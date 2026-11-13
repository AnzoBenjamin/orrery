import { randomBytes } from "node:crypto";
import { GenericContainer, type StartedTestContainer, Wait } from "testcontainers";
import type { StorageConfig } from "./client.ts";

/** Same Garage release as infra/garage/Dockerfile and production. */
export const GARAGE_IMAGE =
  "dxflrs/garage:v2.5.0@sha256:677e5b758e4425a325b811c425c026bf35a4bf42f7ddbaa773de3f4fd779a5a5";

const CONFIG = `metadata_dir = "/var/lib/garage/meta"
data_dir = "/var/lib/garage/data"
db_engine = "lmdb"
replication_factor = 1
rpc_bind_addr = "[::]:3901"
rpc_public_addr = "127.0.0.1:3901"

[s3_api]
s3_region = "garage"
api_bind_addr = "[::]:3900"

[admin]
api_bind_addr = "[::]:3903"
`;

export interface TestGarage {
  config: StorageConfig;
  stop(): Promise<void>;
}

async function admin(base: string, token: string, method: string, path: string, body?: unknown) {
  for (let attempt = 0; ; attempt += 1) {
    const response = await fetch(`${base}/v2/${path}`, {
      method,
      headers: { authorization: `Bearer ${token}`, "content-type": "application/json" },
      ...(body === undefined ? {} : { body: JSON.stringify(body) }),
    });
    if (response.ok) return (await response.json()) as Record<string, unknown>;
    // The cluster refuses some calls for a moment after a layout change.
    if (attempt >= 30)
      throw new Error(`garage ${path}: ${response.status} ${await response.text()}`);
    await new Promise((r) => setTimeout(r, 500));
  }
}

/**
 * Starts a real single-node Garage with one bucket and one key, configured the way
 * infra/garage/bootstrap.sh configures the local stack. Call once per test run.
 */
export async function startTestGarage(): Promise<TestGarage> {
  const adminToken = randomBytes(24).toString("hex");
  const container: StartedTestContainer = await new GenericContainer(GARAGE_IMAGE)
    .withEnvironment({
      GARAGE_RPC_SECRET: randomBytes(32).toString("hex"),
      GARAGE_ADMIN_TOKEN: adminToken,
      GARAGE_METRICS_TOKEN: randomBytes(24).toString("hex"),
    })
    .withCopyContentToContainer([{ content: CONFIG, target: "/etc/garage.toml" }])
    .withExposedPorts(3900, 3903)
    .withCommand(["/garage", "server"])
    // Any answer from the admin API means the node is up; it reports unhealthy until a layout exists.
    .withWaitStrategy(Wait.forHttp("/health", 3903).forStatusCodeMatching(() => true))
    .start();

  const host = container.getHost();
  const base = `http://${host}:${container.getMappedPort(3903)}`;
  const status = await admin(base, adminToken, "GET", "GetClusterStatus");
  const nodes = status.nodes as { id: string }[];
  const nodeId = nodes[0]?.id;
  if (!nodeId) throw new Error("garage reported no nodes");
  await admin(base, adminToken, "POST", "UpdateClusterLayout", {
    roles: [{ id: nodeId, zone: "test", capacity: 1_000_000_000, tags: [] }],
  });
  const layout = await admin(base, adminToken, "GET", "GetClusterLayout");
  await admin(base, adminToken, "POST", "ApplyClusterLayout", {
    version: (layout.version as number) + 1,
  });

  const key = await admin(base, adminToken, "POST", "CreateKey", { name: "orrery-test" });
  const accessKeyId = key.accessKeyId as string;
  const secretAccessKey = key.secretAccessKey as string;
  const bucketName = "orrery-test";
  const bucket = await admin(base, adminToken, "POST", "CreateBucket", {
    globalAlias: bucketName,
  });
  await admin(base, adminToken, "POST", "AllowBucketKey", {
    bucketId: bucket.id,
    accessKeyId,
    permissions: { read: true, write: true, owner: false },
  });

  const s3 = `http://${host}:${container.getMappedPort(3900)}`;
  return {
    config: {
      endpoint: s3,
      publicEndpoint: s3,
      region: "garage",
      bucket: bucketName,
      accessKeyId,
      secretAccessKey,
    },
    stop: async () => {
      await container.stop();
    },
  };
}
