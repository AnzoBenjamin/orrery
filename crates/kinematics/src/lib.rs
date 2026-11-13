//! Orrery's mechanism solver (mechanism-core spec). One implementation shared by the browser
//! (through `kinematics-wasm`) and the engine (through `kinematics-py`).
//!
//! All quantities are SI: meters, radians, seconds.

pub mod schema;
pub mod validate;
