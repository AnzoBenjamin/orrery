//! Python result classes. Per-sample and per-frame numbers are NumPy arrays that take ownership of
//! the solver's buffers (no copy); the reports are small frozen classes with typed fields.

use kinematics::fit::FitResult as Fitted;
use kinematics::mobility::Mobility as MobilityReport;
use kinematics::plausibility::{GrashofClass as Grashof, Plausibility as PlausibilityReport};
use kinematics::simulate::{Singularity as Event, SingularityKind as EventKind};
use numpy::{PyArray1, PyArray2, PyArray3, PyArrayMethods};
use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
use pyo3_stub_gen::derive::{gen_stub_pyclass, gen_stub_pyclass_enum};

/// A rows-by-`cols` array from row-major values, owning the buffer.
pub fn matrix(py: Python<'_>, flat: Vec<f64>, cols: usize) -> PyResult<Py<PyArray2<f64>>> {
    let rows = flat.len().checked_div(cols).unwrap_or(0);
    Ok(PyArray1::from_vec(py, flat).reshape([rows, cols])?.unbind())
}

/// One row per entry of `rows`, which all have `cols` values.
fn stack(py: Python<'_>, rows: &[Vec<f64>], cols: usize) -> PyResult<Py<PyArray2<f64>>> {
    if rows.iter().any(|r| r.len() != cols) {
        return Err(PyValueError::new_err("rows of unequal length"));
    }
    let n = rows.len();
    let flat: Vec<f64> = rows.iter().flatten().copied().collect();
    Ok(PyArray1::from_vec(py, flat).reshape([n, cols])?.unbind())
}

/// The kind of a singularity event in a sweep.
#[gen_stub_pyclass_enum]
#[pyclass(eq, hash, frozen, module = "orrery_kinematics._native")]
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum SingularityKind {
    /// The driver loses influence: the full Jacobian is singular while the joints alone keep
    /// their rank. The reachable range ends there.
    #[pyo3(name = "DEAD_CENTER")]
    DeadCenter,
    /// The output loses mobility: the velocity of the output points passes through zero while
    /// the driver keeps moving, as at a rocker's extreme.
    #[pyo3(name = "LOCKUP")]
    Lockup,
    /// The joints alone lose rank, so assembly branches meet.
    #[pyo3(name = "BIFURCATION")]
    Bifurcation,
}

impl From<EventKind> for SingularityKind {
    fn from(kind: EventKind) -> Self {
        match kind {
            EventKind::DeadCenter => Self::DeadCenter,
            EventKind::Lockup => Self::Lockup,
            EventKind::Bifurcation => Self::Bifurcation,
        }
    }
}

#[gen_stub_pyclass]
#[pyclass(frozen, get_all, module = "orrery_kinematics._native")]
#[derive(Debug, Clone)]
pub struct Singularity {
    /// The swept driver's value at the event.
    drive: f64,
    kind: SingularityKind,
    /// The joints of the bodies that move in the singular direction.
    joints: Vec<String>,
}

impl From<&Event> for Singularity {
    fn from(e: &Event) -> Self {
        Self {
            drive: e.drive,
            kind: e.kind.into(),
            joints: e.joints.clone(),
        }
    }
}

/// A driver sweep.
#[gen_stub_pyclass]
#[pyclass(frozen, get_all, module = "orrery_kinematics._native")]
#[derive(Debug)]
pub struct Simulation {
    /// The swept driver's value per assembled sample, shape `(samples,)`.
    drive: Py<PyArray1<f64>>,
    /// State vectors, shape `(samples, state_size)`.
    states: Py<PyArray2<f64>>,
    /// World positions of every named point (in `Solver.point_names` order), shape
    /// `(samples, points, 3)`, in meters.
    points: Py<PyArray3<f64>>,
    /// Inclusive driver ranges that could be assembled, in sweep order.
    reachable: Vec<(f64, f64)>,
    singularities: Vec<Singularity>,
}

impl Simulation {
    pub fn new(
        py: Python<'_>,
        drive: Vec<f64>,
        states: Vec<f64>,
        state_size: usize,
        points: (Vec<f64>, usize),
        reachable: Vec<(f64, f64)>,
        singularities: &[Event],
    ) -> PyResult<Self> {
        let samples = drive.len();
        Ok(Self {
            drive: PyArray1::from_vec(py, drive).unbind(),
            states: PyArray1::from_vec(py, states)
                .reshape([samples, state_size])?
                .unbind(),
            points: PyArray1::from_vec(py, points.0)
                .reshape([samples, points.1, 3])?
                .unbind(),
            reachable,
            singularities: singularities.iter().map(Singularity::from).collect(),
        })
    }
}

/// A joint whose equations repeat what earlier joints already impose.
#[gen_stub_pyclass]
#[pyclass(frozen, get_all, module = "orrery_kinematics._native")]
#[derive(Debug, Clone)]
pub struct Redundant {
    joint_id: String,
    /// How many of its rows are dependent.
    rows: usize,
}

/// One body's share of a free motion per unit of the motion, in world coordinates: the velocity
/// of the body's local origin and its angular velocity.
#[gen_stub_pyclass]
#[pyclass(frozen, get_all, module = "orrery_kinematics._native")]
#[derive(Debug, Clone)]
pub struct BodyMotion {
    body_id: String,
    translation: (f64, f64, f64),
    rotation: (f64, f64, f64),
}

#[gen_stub_pyclass]
#[pyclass(frozen, get_all, module = "orrery_kinematics._native")]
#[derive(Debug)]
pub struct Mobility {
    /// Grübler–Kutzbach mobility from body and joint counts (may be negative).
    grubler: i64,
    /// Unknowns minus the numerical rank of the joint equations at the pose.
    numerical: usize,
    /// Joints with dependent equations, in graph order.
    redundant: Vec<Redundant>,
    /// Motions the joints and drivers together leave free at the pose, each as the bodies it
    /// moves.
    free_motions: Vec<Vec<BodyMotion>>,
}

impl From<MobilityReport> for Mobility {
    fn from(m: MobilityReport) -> Self {
        let triple = |v: [f64; 3]| (v[0], v[1], v[2]);
        Self {
            grubler: m.grubler,
            numerical: m.numerical,
            redundant: m
                .redundant
                .into_iter()
                .map(|r| Redundant {
                    joint_id: r.joint_id,
                    rows: r.rows,
                })
                .collect(),
            free_motions: m
                .free_motions
                .into_iter()
                .map(|motion| {
                    motion
                        .into_iter()
                        .map(|b| BodyMotion {
                            body_id: b.body_id,
                            translation: triple(b.translation),
                            rotation: triple(b.rotation),
                        })
                        .collect()
                })
                .collect(),
        }
    }
}

/// Grashof class of a four-bar loop.
#[gen_stub_pyclass_enum]
#[pyclass(eq, hash, frozen, module = "orrery_kinematics._native")]
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum GrashofClass {
    /// Shortest link beside the frame: it turns fully, the opposite link rocks.
    #[pyo3(name = "CRANK_ROCKER")]
    CrankRocker,
    /// Shortest link is the frame: both side links turn fully.
    #[pyo3(name = "DOUBLE_CRANK")]
    DoubleCrank,
    /// Grashof with the shortest link as coupler: the coupler turns fully, both sides rock.
    #[pyo3(name = "DOUBLE_ROCKER")]
    DoubleRocker,
    /// s + l = p + q: the loop can fold flat and change branch.
    #[pyo3(name = "CHANGE_POINT")]
    ChangePoint,
    /// s + l > p + q: no link turns fully.
    #[pyo3(name = "TRIPLE_ROCKER")]
    TripleRocker,
}

impl From<Grashof> for GrashofClass {
    fn from(g: Grashof) -> Self {
        match g {
            Grashof::CrankRocker => Self::CrankRocker,
            Grashof::DoubleCrank => Self::DoubleCrank,
            Grashof::DoubleRocker => Self::DoubleRocker,
            Grashof::ChangePoint => Self::ChangePoint,
            Grashof::TripleRocker => Self::TripleRocker,
        }
    }
}

/// The least transmission angle at one floating joint of a loop over the cycle.
#[gen_stub_pyclass]
#[pyclass(frozen, get_all, module = "orrery_kinematics._native")]
#[derive(Debug, Clone)]
pub struct Transmission {
    joint_id: String,
    /// The angle between the two links at the joint, folded to `[0, π/2]` radians: π/2
    /// transmits best, 0 is a toggle.
    min_angle: f64,
    /// The driver value where it occurs.
    at: f64,
}

#[gen_stub_pyclass]
#[pyclass(frozen, get_all, module = "orrery_kinematics._native")]
#[derive(Debug, Clone)]
pub struct FourBarLoop {
    /// Frame, input, coupler, output.
    bodies: (String, String, String, String),
    /// Frame–input, input–coupler, coupler–output, output–frame.
    joints: (String, String, String, String),
    /// Frame, input, coupler, output lengths, in meters.
    lengths: (f64, f64, f64, f64),
    grashof: GrashofClass,
    /// At the input–coupler and coupler–output joints.
    transmission: Vec<Transmission>,
}

/// Two outlines overlapping, over driver ranges.
#[gen_stub_pyclass]
#[pyclass(frozen, get_all, module = "orrery_kinematics._native")]
#[derive(Debug, Clone)]
pub struct Collision {
    bodies: (String, String),
    /// Inclusive driver ranges where they overlap.
    ranges: Vec<(f64, f64)>,
}

/// Where a joint's reaction force flips direction.
#[gen_stub_pyclass]
#[pyclass(frozen, get_all, module = "orrery_kinematics._native")]
#[derive(Debug, Clone)]
pub struct ReactionReversal {
    joint_id: String,
    /// Driver values where the reaction passes through a reversal.
    at: Vec<f64>,
    /// Largest reaction over the cycle, in newtons per newton of load.
    peak: f64,
}

#[gen_stub_pyclass]
#[pyclass(frozen, get_all, module = "orrery_kinematics._native")]
#[derive(Debug)]
pub struct Plausibility {
    loops: Vec<FourBarLoop>,
    collisions: Vec<Collision>,
    /// Length over width of each body with an outline, as `(body_id, ratio)`.
    slenderness: Vec<(String, f64)>,
    reaction_reversals: Vec<ReactionReversal>,
}

impl From<PlausibilityReport> for Plausibility {
    fn from(p: PlausibilityReport) -> Self {
        Self {
            loops: p
                .loops
                .into_iter()
                .map(|l| {
                    let [b0, b1, b2, b3] = l.bodies;
                    let [j0, j1, j2, j3] = l.joints;
                    let [l0, l1, l2, l3] = l.lengths;
                    FourBarLoop {
                        bodies: (b0, b1, b2, b3),
                        joints: (j0, j1, j2, j3),
                        lengths: (l0, l1, l2, l3),
                        grashof: l.grashof.into(),
                        transmission: l
                            .transmission
                            .into_iter()
                            .map(|t| Transmission {
                                joint_id: t.joint_id,
                                min_angle: t.min_angle,
                                at: t.at,
                            })
                            .collect(),
                    }
                })
                .collect(),
            collisions: p
                .collisions
                .into_iter()
                .map(|c| Collision {
                    bodies: c.bodies,
                    ranges: c.ranges,
                })
                .collect(),
            slenderness: p.slenderness,
            reaction_reversals: p
                .reaction_reversals
                .into_iter()
                .map(|r| ReactionReversal {
                    joint_id: r.joint_id,
                    at: r.at,
                    peak: r.peak,
                })
                .collect(),
        }
    }
}

/// A fitted mechanism.
#[gen_stub_pyclass]
#[pyclass(frozen, get_all, module = "orrery_kinematics._native")]
#[derive(Debug)]
pub struct FitResult {
    /// The graph document (JSON text) with the fitted geometry written in and standard
    /// deviations in `uncertainty`.
    mechanism_json: String,
    /// Fitted values of the parameters, in problem order (fixed ones unchanged).
    values: Py<PyArray1<f64>>,
    /// Standard deviations of the parameters (zero for fixed ones).
    sigma: Py<PyArray1<f64>>,
    /// Fitted driver values, shape `(frames, drivers)`.
    drive: Py<PyArray2<f64>>,
    /// Fitted global camera parameters (empty for a plane frame).
    camera_global: Py<PyArray1<f64>>,
    /// Fitted per-frame camera parameters, shape `(frames, parameters per frame)`.
    camera_frames: Py<PyArray2<f64>>,
    /// Each frame's state vector, shape `(frames, state_size)`.
    poses: Py<PyArray2<f64>>,
    /// Fitted minus observed position of each observation in problem order, shape
    /// `(observations, 2)`, in the observation frame.
    residuals: Py<PyArray2<f64>>,
    /// The robust weight each observation ended with (1 for an inlier).
    weights: Py<PyArray1<f64>>,
    /// Root mean square of the observation residual lengths.
    rms: f64,
    /// Final robust cost.
    cost: f64,
    iterations: usize,
}

impl FitResult {
    pub fn new(py: Python<'_>, fitted: Fitted) -> PyResult<Self> {
        let mechanism_json = serde_json::to_string(&fitted.mechanism)
            .map_err(|e| PyValueError::new_err(e.to_string()))?;
        let drivers = fitted.drive.first().map_or(0, Vec::len);
        let per_frame = fitted.camera_frames.first().map_or(0, Vec::len);
        let state_size = fitted.poses.first().map_or(0, Vec::len);
        let residuals: Vec<f64> = fitted.residuals.iter().flat_map(|r| r.residual).collect();
        let weights: Vec<f64> = fitted.residuals.iter().map(|r| r.weight).collect();
        Ok(Self {
            mechanism_json,
            values: PyArray1::from_vec(py, fitted.values).unbind(),
            sigma: PyArray1::from_vec(py, fitted.sigma).unbind(),
            drive: stack(py, &fitted.drive, drivers)?,
            camera_global: PyArray1::from_vec(py, fitted.camera_global).unbind(),
            camera_frames: stack(py, &fitted.camera_frames, per_frame)?,
            poses: stack(py, &fitted.poses, state_size)?,
            residuals: matrix(py, residuals, 2)?,
            weights: PyArray1::from_vec(py, weights).unbind(),
            rms: fitted.rms,
            cost: fitted.cost,
            iterations: fitted.iterations,
        })
    }
}

pub fn register(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_class::<SingularityKind>()?;
    m.add_class::<Singularity>()?;
    m.add_class::<Simulation>()?;
    m.add_class::<Redundant>()?;
    m.add_class::<BodyMotion>()?;
    m.add_class::<Mobility>()?;
    m.add_class::<GrashofClass>()?;
    m.add_class::<Transmission>()?;
    m.add_class::<FourBarLoop>()?;
    m.add_class::<Collision>()?;
    m.add_class::<ReactionReversal>()?;
    m.add_class::<Plausibility>()?;
    m.add_class::<FitResult>()?;
    Ok(())
}
