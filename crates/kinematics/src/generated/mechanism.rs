#![allow(clippy::redundant_closure_call)]
#![allow(clippy::needless_lifetimes)]
#![allow(clippy::match_single_binding)]
#![allow(clippy::clone_on_copy)]

#[doc = "`Body`"]
#[derive(:: serde :: Deserialize, :: serde :: Serialize, Clone, Debug)]
pub struct Body {
    #[serde(skip_serializing_if = "::std::option::Option::is_none")]
    pub cam: ::std::option::Option<CamData>,
    pub confidence: f64,
    #[serde(skip_serializing_if = "::std::option::Option::is_none")]
    pub gear: ::std::option::Option<GearData>,
    pub id: BodyId,
    pub kind: BodyKind,
    pub label: ::std::string::String,
    #[serde(skip_serializing_if = "::std::option::Option::is_none")]
    pub outline: ::std::option::Option<Outline>,
    #[serde(
        rename = "planeId",
        deserialize_with = "::std::option::Option::deserialize"
    )]
    pub plane_id: ::std::option::Option<BodyPlaneId>,
    pub points: ::std::vec::Vec<BodyPoint>,
    #[serde(skip_serializing_if = "::std::option::Option::is_none")]
    pub pulley: ::std::option::Option<PulleyData>,
    pub status: Status,
}
#[doc = "`BodyId`"]
#[derive(:: serde :: Serialize, Clone, Debug, Eq, Hash, Ord, PartialEq, PartialOrd)]
#[serde(transparent)]
pub struct BodyId(::std::string::String);
impl ::std::ops::Deref for BodyId {
    type Target = ::std::string::String;
    fn deref(&self) -> &::std::string::String {
        &self.0
    }
}
impl ::std::convert::From<BodyId> for ::std::string::String {
    fn from(value: BodyId) -> Self {
        value.0
    }
}
impl ::std::str::FromStr for BodyId {
    type Err = self::error::ConversionError;
    fn from_str(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        if value.chars().count() < 1usize {
            return Err("shorter than 1 characters".into());
        }
        Ok(Self(value.to_string()))
    }
}
impl ::std::convert::TryFrom<&str> for BodyId {
    type Error = self::error::ConversionError;
    fn try_from(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<::std::string::String> for BodyId {
    type Error = self::error::ConversionError;
    fn try_from(
        value: ::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl<'de> ::serde::Deserialize<'de> for BodyId {
    fn deserialize<D>(deserializer: D) -> ::std::result::Result<Self, D::Error>
    where
        D: ::serde::Deserializer<'de>,
    {
        ::std::string::String::deserialize(deserializer)?
            .parse()
            .map_err(|e: self::error::ConversionError| {
                <D::Error as ::serde::de::Error>::custom(e.to_string())
            })
    }
}
#[doc = "`BodyKind`"]
#[derive(
    :: serde :: Deserialize,
    :: serde :: Serialize,
    Clone,
    Copy,
    Debug,
    Eq,
    Hash,
    Ord,
    PartialEq,
    PartialOrd,
)]
pub enum BodyKind {
    #[serde(rename = "ground")]
    Ground,
    #[serde(rename = "link")]
    Link,
    #[serde(rename = "slider_block")]
    SliderBlock,
    #[serde(rename = "gear")]
    Gear,
    #[serde(rename = "cam")]
    Cam,
    #[serde(rename = "pulley")]
    Pulley,
    #[serde(rename = "compliant")]
    Compliant,
}
impl ::std::fmt::Display for BodyKind {
    fn fmt(&self, f: &mut ::std::fmt::Formatter<'_>) -> ::std::fmt::Result {
        match *self {
            Self::Ground => f.write_str("ground"),
            Self::Link => f.write_str("link"),
            Self::SliderBlock => f.write_str("slider_block"),
            Self::Gear => f.write_str("gear"),
            Self::Cam => f.write_str("cam"),
            Self::Pulley => f.write_str("pulley"),
            Self::Compliant => f.write_str("compliant"),
        }
    }
}
impl ::std::str::FromStr for BodyKind {
    type Err = self::error::ConversionError;
    fn from_str(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        match value {
            "ground" => Ok(Self::Ground),
            "link" => Ok(Self::Link),
            "slider_block" => Ok(Self::SliderBlock),
            "gear" => Ok(Self::Gear),
            "cam" => Ok(Self::Cam),
            "pulley" => Ok(Self::Pulley),
            "compliant" => Ok(Self::Compliant),
            _ => Err("invalid value".into()),
        }
    }
}
impl ::std::convert::TryFrom<&str> for BodyKind {
    type Error = self::error::ConversionError;
    fn try_from(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<::std::string::String> for BodyKind {
    type Error = self::error::ConversionError;
    fn try_from(
        value: ::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
#[doc = "`BodyPlaneId`"]
#[derive(:: serde :: Serialize, Clone, Debug, Eq, Hash, Ord, PartialEq, PartialOrd)]
#[serde(transparent)]
pub struct BodyPlaneId(::std::string::String);
impl ::std::ops::Deref for BodyPlaneId {
    type Target = ::std::string::String;
    fn deref(&self) -> &::std::string::String {
        &self.0
    }
}
impl ::std::convert::From<BodyPlaneId> for ::std::string::String {
    fn from(value: BodyPlaneId) -> Self {
        value.0
    }
}
impl ::std::str::FromStr for BodyPlaneId {
    type Err = self::error::ConversionError;
    fn from_str(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        if value.chars().count() < 1usize {
            return Err("shorter than 1 characters".into());
        }
        Ok(Self(value.to_string()))
    }
}
impl ::std::convert::TryFrom<&str> for BodyPlaneId {
    type Error = self::error::ConversionError;
    fn try_from(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<::std::string::String> for BodyPlaneId {
    type Error = self::error::ConversionError;
    fn try_from(
        value: ::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl<'de> ::serde::Deserialize<'de> for BodyPlaneId {
    fn deserialize<D>(deserializer: D) -> ::std::result::Result<Self, D::Error>
    where
        D: ::serde::Deserializer<'de>,
    {
        ::std::string::String::deserialize(deserializer)?
            .parse()
            .map_err(|e: self::error::ConversionError| {
                <D::Error as ::serde::de::Error>::custom(e.to_string())
            })
    }
}
#[doc = "`BodyPoint`"]
#[derive(:: serde :: Deserialize, :: serde :: Serialize, Clone, Debug)]
pub struct BodyPoint {
    pub id: BodyPointId,
    pub local: Vec3,
    pub role: PointRole,
}
#[doc = "`BodyPointId`"]
#[derive(:: serde :: Serialize, Clone, Debug, Eq, Hash, Ord, PartialEq, PartialOrd)]
#[serde(transparent)]
pub struct BodyPointId(::std::string::String);
impl ::std::ops::Deref for BodyPointId {
    type Target = ::std::string::String;
    fn deref(&self) -> &::std::string::String {
        &self.0
    }
}
impl ::std::convert::From<BodyPointId> for ::std::string::String {
    fn from(value: BodyPointId) -> Self {
        value.0
    }
}
impl ::std::str::FromStr for BodyPointId {
    type Err = self::error::ConversionError;
    fn from_str(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        if value.chars().count() < 1usize {
            return Err("shorter than 1 characters".into());
        }
        Ok(Self(value.to_string()))
    }
}
impl ::std::convert::TryFrom<&str> for BodyPointId {
    type Error = self::error::ConversionError;
    fn try_from(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<::std::string::String> for BodyPointId {
    type Error = self::error::ConversionError;
    fn try_from(
        value: ::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl<'de> ::serde::Deserialize<'de> for BodyPointId {
    fn deserialize<D>(deserializer: D) -> ::std::result::Result<Self, D::Error>
    where
        D: ::serde::Deserializer<'de>,
    {
        ::std::string::String::deserialize(deserializer)?
            .parse()
            .map_err(|e: self::error::ConversionError| {
                <D::Error as ::serde::de::Error>::custom(e.to_string())
            })
    }
}
#[doc = "`CamData`"]
#[derive(:: serde :: Deserialize, :: serde :: Serialize, Clone, Debug)]
pub struct CamData {
    #[serde(rename = "baseRadius")]
    pub base_radius: f64,
    pub fourier: CamDataFourier,
}
#[doc = "`CamDataFourier`"]
#[derive(:: serde :: Deserialize, :: serde :: Serialize, Clone, Debug)]
pub struct CamDataFourier {
    pub a: ::std::vec::Vec<f64>,
    pub b: ::std::vec::Vec<f64>,
}
#[doc = "`Driver`"]
#[derive(:: serde :: Deserialize, :: serde :: Serialize, Clone, Debug)]
pub struct Driver {
    pub coordinate: DriverCoordinate,
    pub id: DriverId,
    #[serde(rename = "jointId")]
    pub joint_id: DriverJointId,
    pub profile: DriverProfile,
}
#[doc = "`DriverCoordinate`"]
#[derive(
    :: serde :: Deserialize,
    :: serde :: Serialize,
    Clone,
    Copy,
    Debug,
    Eq,
    Hash,
    Ord,
    PartialEq,
    PartialOrd,
)]
pub enum DriverCoordinate {
    #[serde(rename = "angle")]
    Angle,
    #[serde(rename = "displacement")]
    Displacement,
}
impl ::std::fmt::Display for DriverCoordinate {
    fn fmt(&self, f: &mut ::std::fmt::Formatter<'_>) -> ::std::fmt::Result {
        match *self {
            Self::Angle => f.write_str("angle"),
            Self::Displacement => f.write_str("displacement"),
        }
    }
}
impl ::std::str::FromStr for DriverCoordinate {
    type Err = self::error::ConversionError;
    fn from_str(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        match value {
            "angle" => Ok(Self::Angle),
            "displacement" => Ok(Self::Displacement),
            _ => Err("invalid value".into()),
        }
    }
}
impl ::std::convert::TryFrom<&str> for DriverCoordinate {
    type Error = self::error::ConversionError;
    fn try_from(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<::std::string::String> for DriverCoordinate {
    type Error = self::error::ConversionError;
    fn try_from(
        value: ::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
#[doc = "`DriverId`"]
#[derive(:: serde :: Serialize, Clone, Debug, Eq, Hash, Ord, PartialEq, PartialOrd)]
#[serde(transparent)]
pub struct DriverId(::std::string::String);
impl ::std::ops::Deref for DriverId {
    type Target = ::std::string::String;
    fn deref(&self) -> &::std::string::String {
        &self.0
    }
}
impl ::std::convert::From<DriverId> for ::std::string::String {
    fn from(value: DriverId) -> Self {
        value.0
    }
}
impl ::std::str::FromStr for DriverId {
    type Err = self::error::ConversionError;
    fn from_str(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        if value.chars().count() < 1usize {
            return Err("shorter than 1 characters".into());
        }
        Ok(Self(value.to_string()))
    }
}
impl ::std::convert::TryFrom<&str> for DriverId {
    type Error = self::error::ConversionError;
    fn try_from(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<::std::string::String> for DriverId {
    type Error = self::error::ConversionError;
    fn try_from(
        value: ::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl<'de> ::serde::Deserialize<'de> for DriverId {
    fn deserialize<D>(deserializer: D) -> ::std::result::Result<Self, D::Error>
    where
        D: ::serde::Deserializer<'de>,
    {
        ::std::string::String::deserialize(deserializer)?
            .parse()
            .map_err(|e: self::error::ConversionError| {
                <D::Error as ::serde::de::Error>::custom(e.to_string())
            })
    }
}
#[doc = "`DriverJointId`"]
#[derive(:: serde :: Serialize, Clone, Debug, Eq, Hash, Ord, PartialEq, PartialOrd)]
#[serde(transparent)]
pub struct DriverJointId(::std::string::String);
impl ::std::ops::Deref for DriverJointId {
    type Target = ::std::string::String;
    fn deref(&self) -> &::std::string::String {
        &self.0
    }
}
impl ::std::convert::From<DriverJointId> for ::std::string::String {
    fn from(value: DriverJointId) -> Self {
        value.0
    }
}
impl ::std::str::FromStr for DriverJointId {
    type Err = self::error::ConversionError;
    fn from_str(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        if value.chars().count() < 1usize {
            return Err("shorter than 1 characters".into());
        }
        Ok(Self(value.to_string()))
    }
}
impl ::std::convert::TryFrom<&str> for DriverJointId {
    type Error = self::error::ConversionError;
    fn try_from(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<::std::string::String> for DriverJointId {
    type Error = self::error::ConversionError;
    fn try_from(
        value: ::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl<'de> ::serde::Deserialize<'de> for DriverJointId {
    fn deserialize<D>(deserializer: D) -> ::std::result::Result<Self, D::Error>
    where
        D: ::serde::Deserializer<'de>,
    {
        ::std::string::String::deserialize(deserializer)?
            .parse()
            .map_err(|e: self::error::ConversionError| {
                <D::Error as ::serde::de::Error>::custom(e.to_string())
            })
    }
}
#[doc = "`DriverProfile`"]
#[derive(:: serde :: Deserialize, :: serde :: Serialize, Clone, Debug)]
#[serde(tag = "type")]
pub enum DriverProfile {
    #[doc = "ConstantRateProfile"]
    #[serde(rename = "constant_rate")]
    ConstantRate { phase0: f64, rate: f64 },
    #[doc = "SamplesProfile"]
    #[serde(rename = "samples")]
    Samples {
        q: ::std::vec::Vec<f64>,
        t: ::std::vec::Vec<f64>,
    },
}
#[doc = "`FollowerType`"]
#[derive(
    :: serde :: Deserialize,
    :: serde :: Serialize,
    Clone,
    Copy,
    Debug,
    Eq,
    Hash,
    Ord,
    PartialEq,
    PartialOrd,
)]
pub enum FollowerType {
    #[serde(rename = "knife")]
    Knife,
    #[serde(rename = "roller")]
    Roller,
    #[serde(rename = "flat")]
    Flat,
}
impl ::std::fmt::Display for FollowerType {
    fn fmt(&self, f: &mut ::std::fmt::Formatter<'_>) -> ::std::fmt::Result {
        match *self {
            Self::Knife => f.write_str("knife"),
            Self::Roller => f.write_str("roller"),
            Self::Flat => f.write_str("flat"),
        }
    }
}
impl ::std::str::FromStr for FollowerType {
    type Err = self::error::ConversionError;
    fn from_str(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        match value {
            "knife" => Ok(Self::Knife),
            "roller" => Ok(Self::Roller),
            "flat" => Ok(Self::Flat),
            _ => Err("invalid value".into()),
        }
    }
}
impl ::std::convert::TryFrom<&str> for FollowerType {
    type Error = self::error::ConversionError;
    fn try_from(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<::std::string::String> for FollowerType {
    type Error = self::error::ConversionError;
    fn try_from(
        value: ::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
#[doc = "`GearData`"]
#[derive(:: serde :: Deserialize, :: serde :: Serialize, Clone, Debug)]
pub struct GearData {
    pub internal: bool,
    pub module: f64,
    pub teeth: ::std::num::NonZeroU64,
}
#[doc = "`Joint`"]
#[derive(:: serde :: Deserialize, :: serde :: Serialize, Clone, Debug)]
#[serde(tag = "kind")]
pub enum Joint {
    #[doc = "RevoluteJoint"]
    #[serde(rename = "revolute")]
    Revolute {
        #[serde(rename = "anchorA")]
        anchor_a: PointRef,
        #[serde(rename = "anchorB")]
        anchor_b: PointRef,
        #[serde(
            rename = "axisLocalA",
            skip_serializing_if = "::std::option::Option::is_none"
        )]
        axis_local_a: ::std::option::Option<Vec3>,
        #[serde(rename = "bodyA")]
        body_a: JointBodyA,
        #[serde(rename = "bodyB")]
        body_b: JointBodyB,
        confidence: f64,
        id: JointId,
        status: Status,
    },
    #[doc = "PrismaticJoint"]
    #[serde(rename = "prismatic")]
    Prismatic {
        #[serde(rename = "anchorA")]
        anchor_a: PointRef,
        #[serde(rename = "anchorB")]
        anchor_b: PointRef,
        #[serde(rename = "axisLocalA")]
        axis_local_a: Vec3,
        #[serde(rename = "bodyA")]
        body_a: JointBodyA,
        #[serde(rename = "bodyB")]
        body_b: JointBodyB,
        confidence: f64,
        id: JointId,
        #[serde(skip_serializing_if = "::std::option::Option::is_none")]
        limits: ::std::option::Option<(f64, f64)>,
        status: Status,
    },
    #[doc = "PinInSlotJoint"]
    #[serde(rename = "pin_in_slot")]
    PinInSlot {
        #[serde(rename = "bodyA")]
        body_a: JointBodyA,
        #[serde(rename = "bodyB")]
        body_b: JointBodyB,
        confidence: f64,
        id: JointId,
        pin: PointRef,
        slot: SlotCurve,
        status: Status,
    },
    #[doc = "GearMeshJoint"]
    #[serde(rename = "gear_mesh")]
    GearMesh {
        #[serde(rename = "bodyA")]
        body_a: JointBodyA,
        #[serde(rename = "bodyB")]
        body_b: JointBodyB,
        confidence: f64,
        id: JointId,
        phase: f64,
        #[serde(skip_serializing_if = "::std::option::Option::is_none")]
        rack: ::std::option::Option<RackMesh>,
        ratio: f64,
        status: Status,
    },
    #[doc = "BeltJoint"]
    #[serde(rename = "belt")]
    Belt {
        #[serde(rename = "bodyA")]
        body_a: JointBodyA,
        #[serde(rename = "bodyB")]
        body_b: JointBodyB,
        confidence: f64,
        crossed: bool,
        id: JointId,
        ratio: f64,
        status: Status,
    },
    #[doc = "CamFollowerJoint"]
    #[serde(rename = "cam_follower")]
    CamFollower {
        #[serde(rename = "bodyA")]
        body_a: JointBodyA,
        #[serde(rename = "bodyB")]
        body_b: JointBodyB,
        confidence: f64,
        follower: FollowerType,
        #[serde(rename = "followerPoint")]
        follower_point: PointRef,
        id: JointId,
        #[serde(
            rename = "rollerRadius",
            skip_serializing_if = "::std::option::Option::is_none"
        )]
        roller_radius: ::std::option::Option<f64>,
        status: Status,
    },
    #[doc = "SpringJoint"]
    #[serde(rename = "spring")]
    Spring {
        #[serde(rename = "anchorA")]
        anchor_a: PointRef,
        #[serde(rename = "anchorB")]
        anchor_b: PointRef,
        #[serde(rename = "bodyA")]
        body_a: JointBodyA,
        #[serde(rename = "bodyB")]
        body_b: JointBodyB,
        confidence: f64,
        #[serde(rename = "freeLength")]
        free_length: f64,
        id: JointId,
        status: Status,
        stiffness: f64,
    },
    #[doc = "SphericalJoint"]
    #[serde(rename = "spherical")]
    Spherical {
        #[serde(rename = "anchorA")]
        anchor_a: PointRef,
        #[serde(rename = "anchorB")]
        anchor_b: PointRef,
        #[serde(rename = "bodyA")]
        body_a: JointBodyA,
        #[serde(rename = "bodyB")]
        body_b: JointBodyB,
        confidence: f64,
        id: JointId,
        status: Status,
    },
    #[doc = "UniversalJoint"]
    #[serde(rename = "universal")]
    Universal {
        #[serde(rename = "anchorA")]
        anchor_a: PointRef,
        #[serde(rename = "anchorB")]
        anchor_b: PointRef,
        #[serde(
            rename = "axesLocal",
            skip_serializing_if = "::std::option::Option::is_none"
        )]
        axes_local: ::std::option::Option<(Vec3, Vec3)>,
        #[serde(rename = "bodyA")]
        body_a: JointBodyA,
        #[serde(rename = "bodyB")]
        body_b: JointBodyB,
        confidence: f64,
        id: JointId,
        status: Status,
    },
    #[doc = "CylindricalJoint"]
    #[serde(rename = "cylindrical")]
    Cylindrical {
        #[serde(rename = "anchorA")]
        anchor_a: PointRef,
        #[serde(rename = "anchorB")]
        anchor_b: PointRef,
        #[serde(
            rename = "axesLocal",
            skip_serializing_if = "::std::option::Option::is_none"
        )]
        axes_local: ::std::option::Option<(Vec3, Vec3)>,
        #[serde(rename = "bodyA")]
        body_a: JointBodyA,
        #[serde(rename = "bodyB")]
        body_b: JointBodyB,
        confidence: f64,
        id: JointId,
        status: Status,
    },
}
#[doc = "`JointBodyA`"]
#[derive(:: serde :: Serialize, Clone, Debug, Eq, Hash, Ord, PartialEq, PartialOrd)]
#[serde(transparent)]
pub struct JointBodyA(::std::string::String);
impl ::std::ops::Deref for JointBodyA {
    type Target = ::std::string::String;
    fn deref(&self) -> &::std::string::String {
        &self.0
    }
}
impl ::std::convert::From<JointBodyA> for ::std::string::String {
    fn from(value: JointBodyA) -> Self {
        value.0
    }
}
impl ::std::str::FromStr for JointBodyA {
    type Err = self::error::ConversionError;
    fn from_str(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        if value.chars().count() < 1usize {
            return Err("shorter than 1 characters".into());
        }
        Ok(Self(value.to_string()))
    }
}
impl ::std::convert::TryFrom<&str> for JointBodyA {
    type Error = self::error::ConversionError;
    fn try_from(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<::std::string::String> for JointBodyA {
    type Error = self::error::ConversionError;
    fn try_from(
        value: ::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl<'de> ::serde::Deserialize<'de> for JointBodyA {
    fn deserialize<D>(deserializer: D) -> ::std::result::Result<Self, D::Error>
    where
        D: ::serde::Deserializer<'de>,
    {
        ::std::string::String::deserialize(deserializer)?
            .parse()
            .map_err(|e: self::error::ConversionError| {
                <D::Error as ::serde::de::Error>::custom(e.to_string())
            })
    }
}
#[doc = "`JointBodyB`"]
#[derive(:: serde :: Serialize, Clone, Debug, Eq, Hash, Ord, PartialEq, PartialOrd)]
#[serde(transparent)]
pub struct JointBodyB(::std::string::String);
impl ::std::ops::Deref for JointBodyB {
    type Target = ::std::string::String;
    fn deref(&self) -> &::std::string::String {
        &self.0
    }
}
impl ::std::convert::From<JointBodyB> for ::std::string::String {
    fn from(value: JointBodyB) -> Self {
        value.0
    }
}
impl ::std::str::FromStr for JointBodyB {
    type Err = self::error::ConversionError;
    fn from_str(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        if value.chars().count() < 1usize {
            return Err("shorter than 1 characters".into());
        }
        Ok(Self(value.to_string()))
    }
}
impl ::std::convert::TryFrom<&str> for JointBodyB {
    type Error = self::error::ConversionError;
    fn try_from(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<::std::string::String> for JointBodyB {
    type Error = self::error::ConversionError;
    fn try_from(
        value: ::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl<'de> ::serde::Deserialize<'de> for JointBodyB {
    fn deserialize<D>(deserializer: D) -> ::std::result::Result<Self, D::Error>
    where
        D: ::serde::Deserializer<'de>,
    {
        ::std::string::String::deserialize(deserializer)?
            .parse()
            .map_err(|e: self::error::ConversionError| {
                <D::Error as ::serde::de::Error>::custom(e.to_string())
            })
    }
}
#[doc = "`JointId`"]
#[derive(:: serde :: Serialize, Clone, Debug, Eq, Hash, Ord, PartialEq, PartialOrd)]
#[serde(transparent)]
pub struct JointId(::std::string::String);
impl ::std::ops::Deref for JointId {
    type Target = ::std::string::String;
    fn deref(&self) -> &::std::string::String {
        &self.0
    }
}
impl ::std::convert::From<JointId> for ::std::string::String {
    fn from(value: JointId) -> Self {
        value.0
    }
}
impl ::std::str::FromStr for JointId {
    type Err = self::error::ConversionError;
    fn from_str(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        if value.chars().count() < 1usize {
            return Err("shorter than 1 characters".into());
        }
        Ok(Self(value.to_string()))
    }
}
impl ::std::convert::TryFrom<&str> for JointId {
    type Error = self::error::ConversionError;
    fn try_from(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<::std::string::String> for JointId {
    type Error = self::error::ConversionError;
    fn try_from(
        value: ::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl<'de> ::serde::Deserialize<'de> for JointId {
    fn deserialize<D>(deserializer: D) -> ::std::result::Result<Self, D::Error>
    where
        D: ::serde::Deserializer<'de>,
    {
        ::std::string::String::deserialize(deserializer)?
            .parse()
            .map_err(|e: self::error::ConversionError| {
                <D::Error as ::serde::de::Error>::custom(e.to_string())
            })
    }
}
#[doc = "Orrery mechanism graph. Generated from packages/schema; do not edit."]
#[derive(:: serde :: Deserialize, :: serde :: Serialize, Clone, Debug)]
pub struct Mechanism {
    pub bodies: ::std::vec::Vec<Body>,
    pub drivers: ::std::vec::Vec<Driver>,
    pub id: MechanismId,
    pub joints: ::std::vec::Vec<Joint>,
    pub name: ::std::string::String,
    pub planes: ::std::vec::Vec<Plane>,
    pub provenance: Provenance,
    pub scale: Scale,
    #[serde(rename = "schemaVersion")]
    pub schema_version: f64,
    #[serde(
        default,
        skip_serializing_if = ":: std :: collections :: BTreeMap::is_empty"
    )]
    pub uncertainty: ::std::collections::BTreeMap<::std::string::String, f64>,
}
#[doc = "`MechanismId`"]
#[derive(:: serde :: Serialize, Clone, Debug, Eq, Hash, Ord, PartialEq, PartialOrd)]
#[serde(transparent)]
pub struct MechanismId(::std::string::String);
impl ::std::ops::Deref for MechanismId {
    type Target = ::std::string::String;
    fn deref(&self) -> &::std::string::String {
        &self.0
    }
}
impl ::std::convert::From<MechanismId> for ::std::string::String {
    fn from(value: MechanismId) -> Self {
        value.0
    }
}
impl ::std::str::FromStr for MechanismId {
    type Err = self::error::ConversionError;
    fn from_str(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        if value.chars().count() < 1usize {
            return Err("shorter than 1 characters".into());
        }
        Ok(Self(value.to_string()))
    }
}
impl ::std::convert::TryFrom<&str> for MechanismId {
    type Error = self::error::ConversionError;
    fn try_from(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<::std::string::String> for MechanismId {
    type Error = self::error::ConversionError;
    fn try_from(
        value: ::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl<'de> ::serde::Deserialize<'de> for MechanismId {
    fn deserialize<D>(deserializer: D) -> ::std::result::Result<Self, D::Error>
    where
        D: ::serde::Deserializer<'de>,
    {
        ::std::string::String::deserialize(deserializer)?
            .parse()
            .map_err(|e: self::error::ConversionError| {
                <D::Error as ::serde::de::Error>::custom(e.to_string())
            })
    }
}
#[doc = "`Outline`"]
#[derive(:: serde :: Deserialize, :: serde :: Serialize, Clone, Debug)]
pub struct Outline {
    #[serde(skip_serializing_if = "::std::option::Option::is_none")]
    pub offset: ::std::option::Option<f64>,
    #[serde(rename = "polygonLocal")]
    pub polygon_local: ::std::vec::Vec<Vec2>,
    pub thickness: f64,
}
#[doc = "`Plane`"]
#[derive(:: serde :: Deserialize, :: serde :: Serialize, Clone, Debug)]
pub struct Plane {
    pub id: PlaneId,
    #[serde(rename = "normalWorld")]
    pub normal_world: Vec3,
    #[serde(rename = "originWorld")]
    pub origin_world: Vec3,
    #[serde(rename = "xAxisWorld")]
    pub x_axis_world: Vec3,
}
#[doc = "`PlaneId`"]
#[derive(:: serde :: Serialize, Clone, Debug, Eq, Hash, Ord, PartialEq, PartialOrd)]
#[serde(transparent)]
pub struct PlaneId(::std::string::String);
impl ::std::ops::Deref for PlaneId {
    type Target = ::std::string::String;
    fn deref(&self) -> &::std::string::String {
        &self.0
    }
}
impl ::std::convert::From<PlaneId> for ::std::string::String {
    fn from(value: PlaneId) -> Self {
        value.0
    }
}
impl ::std::str::FromStr for PlaneId {
    type Err = self::error::ConversionError;
    fn from_str(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        if value.chars().count() < 1usize {
            return Err("shorter than 1 characters".into());
        }
        Ok(Self(value.to_string()))
    }
}
impl ::std::convert::TryFrom<&str> for PlaneId {
    type Error = self::error::ConversionError;
    fn try_from(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<::std::string::String> for PlaneId {
    type Error = self::error::ConversionError;
    fn try_from(
        value: ::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl<'de> ::serde::Deserialize<'de> for PlaneId {
    fn deserialize<D>(deserializer: D) -> ::std::result::Result<Self, D::Error>
    where
        D: ::serde::Deserializer<'de>,
    {
        ::std::string::String::deserialize(deserializer)?
            .parse()
            .map_err(|e: self::error::ConversionError| {
                <D::Error as ::serde::de::Error>::custom(e.to_string())
            })
    }
}
#[doc = "`PointRef`"]
#[derive(:: serde :: Deserialize, :: serde :: Serialize, Clone, Debug)]
pub struct PointRef {
    #[serde(rename = "bodyId")]
    pub body_id: PointRefBodyId,
    #[serde(rename = "pointId")]
    pub point_id: PointRefPointId,
}
#[doc = "`PointRefBodyId`"]
#[derive(:: serde :: Serialize, Clone, Debug, Eq, Hash, Ord, PartialEq, PartialOrd)]
#[serde(transparent)]
pub struct PointRefBodyId(::std::string::String);
impl ::std::ops::Deref for PointRefBodyId {
    type Target = ::std::string::String;
    fn deref(&self) -> &::std::string::String {
        &self.0
    }
}
impl ::std::convert::From<PointRefBodyId> for ::std::string::String {
    fn from(value: PointRefBodyId) -> Self {
        value.0
    }
}
impl ::std::str::FromStr for PointRefBodyId {
    type Err = self::error::ConversionError;
    fn from_str(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        if value.chars().count() < 1usize {
            return Err("shorter than 1 characters".into());
        }
        Ok(Self(value.to_string()))
    }
}
impl ::std::convert::TryFrom<&str> for PointRefBodyId {
    type Error = self::error::ConversionError;
    fn try_from(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<::std::string::String> for PointRefBodyId {
    type Error = self::error::ConversionError;
    fn try_from(
        value: ::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl<'de> ::serde::Deserialize<'de> for PointRefBodyId {
    fn deserialize<D>(deserializer: D) -> ::std::result::Result<Self, D::Error>
    where
        D: ::serde::Deserializer<'de>,
    {
        ::std::string::String::deserialize(deserializer)?
            .parse()
            .map_err(|e: self::error::ConversionError| {
                <D::Error as ::serde::de::Error>::custom(e.to_string())
            })
    }
}
#[doc = "`PointRefPointId`"]
#[derive(:: serde :: Serialize, Clone, Debug, Eq, Hash, Ord, PartialEq, PartialOrd)]
#[serde(transparent)]
pub struct PointRefPointId(::std::string::String);
impl ::std::ops::Deref for PointRefPointId {
    type Target = ::std::string::String;
    fn deref(&self) -> &::std::string::String {
        &self.0
    }
}
impl ::std::convert::From<PointRefPointId> for ::std::string::String {
    fn from(value: PointRefPointId) -> Self {
        value.0
    }
}
impl ::std::str::FromStr for PointRefPointId {
    type Err = self::error::ConversionError;
    fn from_str(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        if value.chars().count() < 1usize {
            return Err("shorter than 1 characters".into());
        }
        Ok(Self(value.to_string()))
    }
}
impl ::std::convert::TryFrom<&str> for PointRefPointId {
    type Error = self::error::ConversionError;
    fn try_from(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<::std::string::String> for PointRefPointId {
    type Error = self::error::ConversionError;
    fn try_from(
        value: ::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl<'de> ::serde::Deserialize<'de> for PointRefPointId {
    fn deserialize<D>(deserializer: D) -> ::std::result::Result<Self, D::Error>
    where
        D: ::serde::Deserializer<'de>,
    {
        ::std::string::String::deserialize(deserializer)?
            .parse()
            .map_err(|e: self::error::ConversionError| {
                <D::Error as ::serde::de::Error>::custom(e.to_string())
            })
    }
}
#[doc = "`PointRole`"]
#[derive(
    :: serde :: Deserialize,
    :: serde :: Serialize,
    Clone,
    Copy,
    Debug,
    Eq,
    Hash,
    Ord,
    PartialEq,
    PartialOrd,
)]
pub enum PointRole {
    #[serde(rename = "joint_anchor")]
    JointAnchor,
    #[serde(rename = "tracked")]
    Tracked,
    #[serde(rename = "output")]
    Output,
    #[serde(rename = "hole")]
    Hole,
}
impl ::std::fmt::Display for PointRole {
    fn fmt(&self, f: &mut ::std::fmt::Formatter<'_>) -> ::std::fmt::Result {
        match *self {
            Self::JointAnchor => f.write_str("joint_anchor"),
            Self::Tracked => f.write_str("tracked"),
            Self::Output => f.write_str("output"),
            Self::Hole => f.write_str("hole"),
        }
    }
}
impl ::std::str::FromStr for PointRole {
    type Err = self::error::ConversionError;
    fn from_str(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        match value {
            "joint_anchor" => Ok(Self::JointAnchor),
            "tracked" => Ok(Self::Tracked),
            "output" => Ok(Self::Output),
            "hole" => Ok(Self::Hole),
            _ => Err("invalid value".into()),
        }
    }
}
impl ::std::convert::TryFrom<&str> for PointRole {
    type Error = self::error::ConversionError;
    fn try_from(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<::std::string::String> for PointRole {
    type Error = self::error::ConversionError;
    fn try_from(
        value: ::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
#[doc = "`Provenance`"]
#[derive(:: serde :: Deserialize, :: serde :: Serialize, Clone, Debug)]
pub struct Provenance {
    #[serde(
        rename = "analysisId",
        skip_serializing_if = "::std::option::Option::is_none"
    )]
    pub analysis_id: ::std::option::Option<ProvenanceAnalysisId>,
    #[serde(rename = "createdBy")]
    pub created_by: ProvenanceCreatedBy,
    #[serde(
        rename = "engineVersion",
        skip_serializing_if = "::std::option::Option::is_none"
    )]
    pub engine_version: ::std::option::Option<::std::string::String>,
    #[serde(rename = "footageIds")]
    pub footage_ids: ::std::vec::Vec<ProvenanceFootageIdsItem>,
}
#[doc = "`ProvenanceAnalysisId`"]
#[derive(:: serde :: Serialize, Clone, Debug, Eq, Hash, Ord, PartialEq, PartialOrd)]
#[serde(transparent)]
pub struct ProvenanceAnalysisId(::std::string::String);
impl ::std::ops::Deref for ProvenanceAnalysisId {
    type Target = ::std::string::String;
    fn deref(&self) -> &::std::string::String {
        &self.0
    }
}
impl ::std::convert::From<ProvenanceAnalysisId> for ::std::string::String {
    fn from(value: ProvenanceAnalysisId) -> Self {
        value.0
    }
}
impl ::std::str::FromStr for ProvenanceAnalysisId {
    type Err = self::error::ConversionError;
    fn from_str(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        if value.chars().count() < 1usize {
            return Err("shorter than 1 characters".into());
        }
        Ok(Self(value.to_string()))
    }
}
impl ::std::convert::TryFrom<&str> for ProvenanceAnalysisId {
    type Error = self::error::ConversionError;
    fn try_from(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<::std::string::String> for ProvenanceAnalysisId {
    type Error = self::error::ConversionError;
    fn try_from(
        value: ::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl<'de> ::serde::Deserialize<'de> for ProvenanceAnalysisId {
    fn deserialize<D>(deserializer: D) -> ::std::result::Result<Self, D::Error>
    where
        D: ::serde::Deserializer<'de>,
    {
        ::std::string::String::deserialize(deserializer)?
            .parse()
            .map_err(|e: self::error::ConversionError| {
                <D::Error as ::serde::de::Error>::custom(e.to_string())
            })
    }
}
#[doc = "`ProvenanceCreatedBy`"]
#[derive(
    :: serde :: Deserialize,
    :: serde :: Serialize,
    Clone,
    Copy,
    Debug,
    Eq,
    Hash,
    Ord,
    PartialEq,
    PartialOrd,
)]
pub enum ProvenanceCreatedBy {
    #[serde(rename = "engine")]
    Engine,
    #[serde(rename = "user")]
    User,
    #[serde(rename = "lab")]
    Lab,
}
impl ::std::fmt::Display for ProvenanceCreatedBy {
    fn fmt(&self, f: &mut ::std::fmt::Formatter<'_>) -> ::std::fmt::Result {
        match *self {
            Self::Engine => f.write_str("engine"),
            Self::User => f.write_str("user"),
            Self::Lab => f.write_str("lab"),
        }
    }
}
impl ::std::str::FromStr for ProvenanceCreatedBy {
    type Err = self::error::ConversionError;
    fn from_str(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        match value {
            "engine" => Ok(Self::Engine),
            "user" => Ok(Self::User),
            "lab" => Ok(Self::Lab),
            _ => Err("invalid value".into()),
        }
    }
}
impl ::std::convert::TryFrom<&str> for ProvenanceCreatedBy {
    type Error = self::error::ConversionError;
    fn try_from(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<::std::string::String> for ProvenanceCreatedBy {
    type Error = self::error::ConversionError;
    fn try_from(
        value: ::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
#[doc = "`ProvenanceFootageIdsItem`"]
#[derive(:: serde :: Serialize, Clone, Debug, Eq, Hash, Ord, PartialEq, PartialOrd)]
#[serde(transparent)]
pub struct ProvenanceFootageIdsItem(::std::string::String);
impl ::std::ops::Deref for ProvenanceFootageIdsItem {
    type Target = ::std::string::String;
    fn deref(&self) -> &::std::string::String {
        &self.0
    }
}
impl ::std::convert::From<ProvenanceFootageIdsItem> for ::std::string::String {
    fn from(value: ProvenanceFootageIdsItem) -> Self {
        value.0
    }
}
impl ::std::str::FromStr for ProvenanceFootageIdsItem {
    type Err = self::error::ConversionError;
    fn from_str(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        if value.chars().count() < 1usize {
            return Err("shorter than 1 characters".into());
        }
        Ok(Self(value.to_string()))
    }
}
impl ::std::convert::TryFrom<&str> for ProvenanceFootageIdsItem {
    type Error = self::error::ConversionError;
    fn try_from(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<::std::string::String> for ProvenanceFootageIdsItem {
    type Error = self::error::ConversionError;
    fn try_from(
        value: ::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl<'de> ::serde::Deserialize<'de> for ProvenanceFootageIdsItem {
    fn deserialize<D>(deserializer: D) -> ::std::result::Result<Self, D::Error>
    where
        D: ::serde::Deserializer<'de>,
    {
        ::std::string::String::deserialize(deserializer)?
            .parse()
            .map_err(|e: self::error::ConversionError| {
                <D::Error as ::serde::de::Error>::custom(e.to_string())
            })
    }
}
#[doc = "`PulleyData`"]
#[derive(:: serde :: Deserialize, :: serde :: Serialize, Clone, Debug)]
pub struct PulleyData {
    pub radius: f64,
}
#[doc = "`RackMesh`"]
#[derive(:: serde :: Deserialize, :: serde :: Serialize, Clone, Debug)]
pub struct RackMesh {
    #[serde(rename = "axisLocalB")]
    pub axis_local_b: Vec3,
}
#[doc = "`Scale`"]
#[derive(:: serde :: Deserialize, :: serde :: Serialize, Clone, Debug)]
pub struct Scale {
    #[serde(rename = "metersPerUnit")]
    pub meters_per_unit: f64,
    #[serde(skip_serializing_if = "::std::option::Option::is_none")]
    pub sigma: ::std::option::Option<f64>,
    pub source: ScaleSource,
}
#[doc = "`ScaleSource`"]
#[derive(
    :: serde :: Deserialize,
    :: serde :: Serialize,
    Clone,
    Copy,
    Debug,
    Eq,
    Hash,
    Ord,
    PartialEq,
    PartialOrd,
)]
pub enum ScaleSource {
    #[serde(rename = "user_measurement")]
    UserMeasurement,
    #[serde(rename = "reference_object")]
    ReferenceObject,
    #[serde(rename = "intrinsics")]
    Intrinsics,
    #[serde(rename = "unscaled")]
    Unscaled,
}
impl ::std::fmt::Display for ScaleSource {
    fn fmt(&self, f: &mut ::std::fmt::Formatter<'_>) -> ::std::fmt::Result {
        match *self {
            Self::UserMeasurement => f.write_str("user_measurement"),
            Self::ReferenceObject => f.write_str("reference_object"),
            Self::Intrinsics => f.write_str("intrinsics"),
            Self::Unscaled => f.write_str("unscaled"),
        }
    }
}
impl ::std::str::FromStr for ScaleSource {
    type Err = self::error::ConversionError;
    fn from_str(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        match value {
            "user_measurement" => Ok(Self::UserMeasurement),
            "reference_object" => Ok(Self::ReferenceObject),
            "intrinsics" => Ok(Self::Intrinsics),
            "unscaled" => Ok(Self::Unscaled),
            _ => Err("invalid value".into()),
        }
    }
}
impl ::std::convert::TryFrom<&str> for ScaleSource {
    type Error = self::error::ConversionError;
    fn try_from(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<::std::string::String> for ScaleSource {
    type Error = self::error::ConversionError;
    fn try_from(
        value: ::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
#[doc = "`SlotCurve`"]
#[derive(:: serde :: Deserialize, :: serde :: Serialize, Clone, Debug)]
#[serde(tag = "type")]
pub enum SlotCurve {
    #[doc = "LineSegmentSlot"]
    #[serde(rename = "line_segment")]
    LineSegment { end: Vec2, start: Vec2 },
    #[doc = "CircularArcSlot"]
    #[serde(rename = "circular_arc")]
    CircularArc {
        #[serde(rename = "angleEnd")]
        angle_end: f64,
        #[serde(rename = "angleStart")]
        angle_start: f64,
        center: Vec2,
        radius: f64,
    },
    #[doc = "CubicBsplineSlot"]
    #[serde(rename = "cubic_bspline")]
    CubicBspline {
        #[serde(rename = "controlPoints")]
        control_points: ::std::vec::Vec<Vec2>,
        knots: ::std::vec::Vec<f64>,
    },
}
#[doc = "`Status`"]
#[derive(
    :: serde :: Deserialize,
    :: serde :: Serialize,
    Clone,
    Copy,
    Debug,
    Eq,
    Hash,
    Ord,
    PartialEq,
    PartialOrd,
)]
pub enum Status {
    #[serde(rename = "observed")]
    Observed,
    #[serde(rename = "inferred")]
    Inferred,
    #[serde(rename = "user")]
    User,
    #[serde(rename = "candidate")]
    Candidate,
}
impl ::std::fmt::Display for Status {
    fn fmt(&self, f: &mut ::std::fmt::Formatter<'_>) -> ::std::fmt::Result {
        match *self {
            Self::Observed => f.write_str("observed"),
            Self::Inferred => f.write_str("inferred"),
            Self::User => f.write_str("user"),
            Self::Candidate => f.write_str("candidate"),
        }
    }
}
impl ::std::str::FromStr for Status {
    type Err = self::error::ConversionError;
    fn from_str(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        match value {
            "observed" => Ok(Self::Observed),
            "inferred" => Ok(Self::Inferred),
            "user" => Ok(Self::User),
            "candidate" => Ok(Self::Candidate),
            _ => Err("invalid value".into()),
        }
    }
}
impl ::std::convert::TryFrom<&str> for Status {
    type Error = self::error::ConversionError;
    fn try_from(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<::std::string::String> for Status {
    type Error = self::error::ConversionError;
    fn try_from(
        value: ::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
#[doc = "`Vec2`"]
#[derive(:: serde :: Deserialize, :: serde :: Serialize, Clone, Debug)]
pub struct Vec2 {
    pub x: f64,
    pub y: f64,
}
#[doc = "`Vec3`"]
#[derive(:: serde :: Deserialize, :: serde :: Serialize, Clone, Debug)]
pub struct Vec3 {
    pub x: f64,
    pub y: f64,
    pub z: f64,
}
#[doc = " Error types."]
pub mod error {
    #[doc = r" Error from a `TryFrom` or `FromStr` implementation."]
    pub struct ConversionError(::std::borrow::Cow<'static, str>);
    impl ::std::error::Error for ConversionError {}
    impl ::std::fmt::Display for ConversionError {
        fn fmt(&self, f: &mut ::std::fmt::Formatter<'_>) -> Result<(), ::std::fmt::Error> {
            ::std::fmt::Display::fmt(&self.0, f)
        }
    }
    impl ::std::fmt::Debug for ConversionError {
        fn fmt(&self, f: &mut ::std::fmt::Formatter<'_>) -> Result<(), ::std::fmt::Error> {
            ::std::fmt::Debug::fmt(&self.0, f)
        }
    }
    impl From<&'static str> for ConversionError {
        fn from(value: &'static str) -> Self {
            Self(value.into())
        }
    }
    impl From<String> for ConversionError {
        fn from(value: String) -> Self {
            Self(value.into())
        }
    }
}
