#!/bin/sh
# Brings a fresh single-node Garage to a usable state: assigns the node a layout role, imports the
# application's S3 key, creates the bucket, grants the key, and applies the CORS rules that browser
# multipart uploads need (Uppy reads the ETag header of each part). Every step is idempotent, so the
# script runs on every `make up`.
set -eu

: "${GARAGE_ADMIN_URL:?}" "${GARAGE_ADMIN_TOKEN:?}" "${S3_ACCESS_KEY_ID:?}" "${S3_SECRET_ACCESS_KEY:?}"
: "${S3_BUCKET:?}" "${S3_CORS_ORIGINS:?}" "${GARAGE_CAPACITY_BYTES:?}"

api() {
  method=$1 endpoint=$2
  shift 2
  curl -fsS --retry 30 --retry-connrefused --retry-delay 1 -X "$method" \
    -H "Authorization: Bearer ${GARAGE_ADMIN_TOKEN}" -H 'Content-Type: application/json' \
    "${GARAGE_ADMIN_URL}/v2/${endpoint}" "$@"
}

status=$(api GET GetClusterStatus)
node_id=$(printf '%s' "$status" | jq -r '.nodes[0].id')
if [ "$(printf '%s' "$status" | jq -r '.nodes[0].role')" = "null" ]; then
  echo "garage-bootstrap: assigning layout role to node ${node_id}"
  api POST UpdateClusterLayout -d "$(jq -n --arg id "$node_id" --argjson cap "$GARAGE_CAPACITY_BYTES" \
    '{roles: [{id: $id, zone: "local", capacity: $cap, tags: []}]}')" >/dev/null
  version=$(api GET GetClusterLayout | jq '.version + 1')
  api POST ApplyClusterLayout -d "{\"version\": ${version}}" >/dev/null
fi

# The cluster can serve requests once the new layout has propagated.
curl -fsS --retry 30 --retry-all-errors --retry-delay 1 -o /dev/null "${GARAGE_ADMIN_URL}/health"

if ! api GET "GetKeyInfo?id=${S3_ACCESS_KEY_ID}" >/dev/null 2>&1; then
  echo "garage-bootstrap: importing application key"
  api POST ImportKey -d "$(jq -n --arg id "$S3_ACCESS_KEY_ID" --arg secret "$S3_SECRET_ACCESS_KEY" \
    '{accessKeyId: $id, secretAccessKey: $secret, name: "orrery-app"}')" >/dev/null
fi

if ! bucket=$(api GET "GetBucketInfo?globalAlias=${S3_BUCKET}" 2>/dev/null); then
  echo "garage-bootstrap: creating bucket ${S3_BUCKET}"
  bucket=$(api POST CreateBucket -d "{\"globalAlias\": \"${S3_BUCKET}\"}")
fi
bucket_id=$(printf '%s' "$bucket" | jq -r '.id')

api POST AllowBucketKey -d "$(jq -n --arg b "$bucket_id" --arg k "$S3_ACCESS_KEY_ID" \
  '{bucketId: $b, accessKeyId: $k, permissions: {read: true, write: true, owner: false}}')" >/dev/null

api POST "UpdateBucket?id=${bucket_id}" -d "$(jq -n --arg origins "$S3_CORS_ORIGINS" '{corsRules: [{
  ID: "browser-uploads",
  AllowedOrigin: ($origins | split(",")),
  AllowedMethod: ["GET", "HEAD", "PUT"],
  AllowedHeader: ["*"],
  ExposeHeader: ["ETag"],
  MaxAgeSeconds: 3600
}]}')" >/dev/null

echo "garage-bootstrap: bucket ${S3_BUCKET} ready"
