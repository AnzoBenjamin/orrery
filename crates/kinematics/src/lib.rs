//! Orrery's mechanism solver (mechanism-core spec). One implementation shared by the browser
//! (through `kinematics-wasm`) and the engine (through `kinematics-py`).
//!
//! All quantities are SI: meters, radians, seconds.

pub mod assembly;
pub mod constraint;
pub mod curves;
pub mod dual;
pub mod energy;
pub mod error;
pub mod mobility;
pub mod model;
pub mod motion;
pub mod planar;
pub mod plausibility;
pub mod schema;
pub mod simulate;
pub mod validate;

pub use assembly::{Assembly, AssemblyOptions, LinearPath};
pub use error::SolverError;
pub use model::Model;
