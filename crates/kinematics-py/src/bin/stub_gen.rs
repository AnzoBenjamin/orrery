//! Writes the type stubs of `orrery_kinematics._native` (`pnpm codegen`).

fn main() -> pyo3_stub_gen::Result<()> {
    kinematics_py::stub_info()?.generate()?;
    Ok(())
}
