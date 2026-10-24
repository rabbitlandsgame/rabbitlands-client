//! Moor Pony rider math only. Godot still owns animation sampling and scene objects.
//! Layouts are documented in the accompanying README and validated before publication.
use crate::{INVALID, Rig};
use std::f64::consts::{PI, TAU};

pub const BONE_SLOTS: usize = 38;
pub const CONSTANTS: usize = 113;
pub const SAMPLE: usize = 14;
pub const MAX_RIDERS: usize = 4096;

#[derive(Clone, Copy, Debug, Default)]
struct V(f64, f64, f64);
impl V {
    fn read(v: &[f64]) -> Self {
        Self(v[0], v[1], v[2])
    }
    fn add(self, b: Self) -> Self {
        Self(self.0 + b.0, self.1 + b.1, self.2 + b.2)
    }
    fn sub(self, b: Self) -> Self {
        Self(self.0 - b.0, self.1 - b.1, self.2 - b.2)
    }
    fn mul(self, s: f64) -> Self {
        Self(self.0 * s, self.1 * s, self.2 * s)
    }
    fn dot(self, b: Self) -> f64 {
        self.0 * b.0 + self.1 * b.1 + self.2 * b.2
    }
    fn cross(self, b: Self) -> Self {
        Self(
            self.1 * b.2 - self.2 * b.1,
            self.2 * b.0 - self.0 * b.2,
            self.0 * b.1 - self.1 * b.0,
        )
    }
    fn len2(self) -> f64 {
        self.dot(self)
    }
    fn len(self) -> f64 {
        self.len2().sqrt()
    }
    fn unit(self) -> Self {
        let n = self.len();
        if n == 0.0 {
            Self::default()
        } else {
            self.mul(1.0 / n)
        }
    }
    fn write(self, out: &mut Vec<f64>) {
        out.extend([self.0, self.1, self.2]);
    }
}

#[derive(Clone, Copy, Debug)]
struct Q(f64, f64, f64, f64);
impl Q {
    fn read(v: &[f64]) -> Self {
        Self(v[0], v[1], v[2], v[3])
    }
    fn dot(self, b: Self) -> f64 {
        self.0 * b.0 + self.1 * b.1 + self.2 * b.2 + self.3 * b.3
    }
    fn mul(self, s: f64) -> Self {
        Self(self.0 * s, self.1 * s, self.2 * s, self.3 * s)
    }
    fn add(self, b: Self) -> Self {
        Self(self.0 + b.0, self.1 + b.1, self.2 + b.2, self.3 + b.3)
    }
    fn unit(self) -> Self {
        self.mul(1.0 / self.dot(self).sqrt())
    }
    fn axis(v: V, angle: f64) -> Self {
        let s = (angle * 0.5).sin();
        let v = v.unit();
        Self(v.0 * s, v.1 * s, v.2 * s, (angle * 0.5).cos())
    }
    fn arc(a: V, b: V) -> Self {
        let d = a.dot(b);
        // Match the pinned single-precision Godot 4.7 shortest-arc branches.
        if d.abs() > 0.99999975 {
            if d >= 0. {
                return Self(0., 0., 0., 1.);
            }
            let axis = a
                .cross(if a.0.abs() <= a.1.abs() && a.0.abs() <= a.2.abs() {
                    V(1., 0., 0.)
                } else {
                    V(0., 1., 0.)
                })
                .unit();
            return Self(axis.0, axis.1, axis.2, 0.);
        }
        let c = a.cross(b);
        let s = ((1.0 + d) * 2.0).sqrt();
        Self(c.0 / s, c.1 / s, c.2 / s, s * 0.5).unit()
    }
    fn slerp(self, mut b: Self, t: f64) -> Self {
        let mut d = self.dot(b);
        if d < 0.0 {
            d = -d;
            b = b.mul(-1.0);
        }
        if 1.0 - d > 0.00001 {
            let a = d.clamp(-1.0, 1.0).acos();
            let s = a.sin();
            self.mul(((1.0 - t) * a).sin() / s)
                .add(b.mul((t * a).sin() / s))
        } else {
            self.mul(1.0 - t).add(b.mul(t))
        }
    }
    fn write(self, out: &mut Vec<f64>) {
        out.extend([self.0, self.1, self.2, self.3]);
    }
}

/// Three column vectors, matching the Phase 4 affine buffer contract.
#[derive(Clone, Copy, Debug)]
struct M(V, V, V);
impl M {
    fn identity() -> Self {
        Self(V(1., 0., 0.), V(0., 1., 0.), V(0., 0., 1.))
    }
    fn read(a: &[f64]) -> Self {
        Self(V::read(a), V::read(&a[3..]), V::read(&a[6..]))
    }
    fn vec(self, v: V) -> V {
        self.0.mul(v.0).add(self.1.mul(v.1)).add(self.2.mul(v.2))
    }
    fn mul(self, b: Self) -> Self {
        Self(self.vec(b.0), self.vec(b.1), self.vec(b.2))
    }
    fn det(self) -> f64 {
        self.0.dot(self.1.cross(self.2))
    }
    fn inverse(self) -> Self {
        let d = self.det();
        let a = self.1.cross(self.2).mul(1.0 / d);
        let b = self.2.cross(self.0).mul(1.0 / d);
        let c = self.0.cross(self.1).mul(1.0 / d);
        Self(V(a.0, b.0, c.0), V(a.1, b.1, c.1), V(a.2, b.2, c.2))
    }
    fn ortho(self) -> Self {
        let x = self.0.unit();
        let y = self.1.sub(x.mul(x.dot(self.1))).unit();
        let z = self
            .2
            .sub(x.mul(x.dot(self.2)))
            .sub(y.mul(y.dot(self.2)))
            .unit();
        Self(x, y, z)
    }
    fn quat(q: Q) -> Self {
        let Q(x, y, z, w) = q;
        let d = q.dot(q);
        let s = 2.0 / d;
        Self(
            V(
                1. - s * (y * y + z * z),
                s * (x * y + z * w),
                s * (x * z - y * w),
            ),
            V(
                s * (x * y - z * w),
                1. - s * (x * x + z * z),
                s * (y * z + x * w),
            ),
            V(
                s * (x * z + y * w),
                s * (y * z - x * w),
                1. - s * (x * x + y * y),
            ),
        )
    }
    fn rotation(self) -> Q {
        let mut m = self.ortho();
        if m.det() < 0.0 {
            m = Self(m.0.mul(-1.), m.1.mul(-1.), m.2.mul(-1.));
        }
        let r = [
            [m.0.0, m.1.0, m.2.0],
            [m.0.1, m.1.1, m.2.1],
            [m.0.2, m.1.2, m.2.2],
        ];
        let t = r[0][0] + r[1][1] + r[2][2];
        if t > 0.0 {
            let s = (t + 1.0).sqrt();
            let k = 0.5 / s;
            Q(
                (r[2][1] - r[1][2]) * k,
                (r[0][2] - r[2][0]) * k,
                (r[1][0] - r[0][1]) * k,
                s * 0.5,
            )
        } else {
            let i = if r[0][0] < r[1][1] {
                if r[1][1] < r[2][2] { 2 } else { 1 }
            } else if r[0][0] < r[2][2] {
                2
            } else {
                0
            };
            let j = (i + 1) % 3;
            let k = (i + 2) % 3;
            let s = (r[i][i] - r[j][j] - r[k][k] + 1.).sqrt();
            let mut q = [0.; 4];
            q[i] = s * 0.5;
            let z = 0.5 / s;
            q[3] = (r[k][j] - r[j][k]) * z;
            q[j] = (r[j][i] + r[i][j]) * z;
            q[k] = (r[k][i] + r[i][k]) * z;
            Q::read(&q)
        }
    }
    fn write(self, out: &mut Vec<f64>) {
        self.0.write(out);
        self.1.write(out);
        self.2.write(out);
    }
}

#[derive(Clone, Copy, Debug)]
struct A {
    b: M,
    p: V,
}
impl A {
    fn identity() -> Self {
        Self {
            b: M::identity(),
            p: V::default(),
        }
    }
    fn read(v: &[f64]) -> Self {
        Self {
            b: M::read(v),
            p: V::read(&v[9..]),
        }
    }
    fn mul(self, c: Self) -> Self {
        Self {
            b: self.b.mul(c.b),
            p: self.b.vec(c.p).add(self.p),
        }
    }
    fn inverse(self) -> Self {
        let b = self.b.inverse();
        Self {
            b,
            p: b.vec(self.p.mul(-1.)),
        }
    }
    fn point(self, p: V) -> V {
        self.b.vec(p).add(self.p)
    }
    fn write(self, out: &mut Vec<f64>) {
        self.b.write(out);
        self.p.write(out);
    }
}

#[derive(Clone)]
pub struct Rider {
    pub rig: u64,
    bones: [usize; BONE_SLOTS],
    constants: Vec<f64>,
    thumbs: Vec<(usize, Q)>,
    // Reused local/global pose buffers. No scene references or worker ownership.
    local: Vec<A>,
    global: Vec<A>,
    rotations: Vec<Q>,
    scales: Vec<V>,
    order: Vec<usize>,
}
impl Rider {
    pub fn new(
        rig_handle: u64,
        rig: &Rig,
        bones: &[i32],
        constants: &[f64],
        thumbs: &[i32],
        grips: &[f64],
    ) -> Result<Self, i32> {
        let n = rig.parents.len();
        if bones.len() != BONE_SLOTS
            || constants.len() != CONSTANTS
            || grips.len() != thumbs.len() * 4
            || thumbs.len() > n
            || !constants.iter().chain(grips).all(|x| x.is_finite())
        {
            return Err(INVALID);
        }
        let mut slots = [0; BONE_SLOTS];
        for (i, &bone) in bones.iter().enumerate() {
            if bone < 0 || bone as usize >= n || slots[..i].contains(&(bone as usize)) {
                return Err(INVALID);
            }
            slots[i] = bone as usize;
        }
        let mut thumb_data = Vec::new();
        for (i, &bone) in thumbs.iter().enumerate() {
            let q = Q::read(&grips[i * 4..]);
            if bone < 0
                || bone as usize >= n
                || q.dot(q) < 1e-12
                || thumb_data.iter().any(|(b, _)| *b == bone as usize)
            {
                return Err(INVALID);
            }
            thumb_data.push((bone as usize, q.unit()));
        }
        for start in [3, 15] {
            if A::read(&constants[start..]).b.det().abs() < 1e-12 {
                return Err(INVALID);
            }
        }
        for start in [27, 36] {
            if M::read(&constants[start..]).det().abs() < 1e-12 {
                return Err(INVALID);
            }
        }
        for start in (45..81).step_by(3) {
            if V::read(&constants[start..]).len2() < 1e-10 {
                return Err(INVALID);
            }
        }
        if constants[82] < 0. || constants[82] > 1. || constants[83] < 0. || constants[83] > 1. {
            return Err(INVALID);
        }
        let mut order = Vec::with_capacity(n);
        let mut added = vec![false; n];
        while order.len() < n {
            let before = order.len();
            for bone in 0..n {
                let p = rig.parents[bone];
                if !added[bone] && (p < 0 || added[p as usize]) {
                    added[bone] = true;
                    order.push(bone);
                }
            }
            if before == order.len() {
                return Err(INVALID);
            }
        }
        let mut out = Self {
            rig: rig_handle,
            bones: slots,
            constants: constants.to_vec(),
            thumbs: thumb_data,
            local: vec![A::identity(); n],
            global: vec![A::identity(); n],
            rotations: vec![Q(0., 0., 0., 1.); n],
            scales: vec![V(1., 1., 1.); n],
            order,
        };
        out.reset(rig);
        out.fk(rig);
        // Reject degenerate limbs once; live input failures must fall back before scene mutation.
        for side in 0..2 {
            let s = 2 + 18 * side;
            for k in [0, 3] {
                let a = out.global[out.bones[s + k]].p;
                let b = out.global[out.bones[s + k + 1]].p;
                let c = out.global[out.bones[s + k + 2]].p;
                if a.sub(b).len() < 0.0002 || b.sub(c).len() < 0.0002 {
                    return Err(INVALID);
                }
            }
        }
        Ok(out)
    }
    fn reset(&mut self, rig: &Rig) {
        for i in 0..self.local.len() {
            let v = &rig.neutral_pose[i * 10..];
            let q = Q::read(&v[3..]);
            let s = V::read(&v[7..]);
            let r = M::quat(q);
            self.rotations[i] = q;
            self.scales[i] = s;
            self.local[i] = A {
                b: M(r.0.mul(s.0), r.1.mul(s.1), r.2.mul(s.2)),
                p: V::read(v),
            };
        }
    }
    fn fk(&mut self, rig: &Rig) {
        // Godot 4 bone pose is the complete parent-local pose, not rest * pose.
        // The separately registered rest is intentionally not multiplied here.
        for &i in &self.order {
            let p = rig.parents[i];
            self.global[i] = if p < 0 {
                self.local[i]
            } else {
                self.global[p as usize].mul(self.local[i])
            };
        }
    }
    fn set_q(&mut self, bone: usize, q: Q) {
        let q = q.unit();
        let r = M::quat(q);
        let s = self.scales[bone];
        self.rotations[bone] = q;
        self.local[bone].b = M(r.0.mul(s.0), r.1.mul(s.1), r.2.mul(s.2));
    }
    fn set_basis(&mut self, rig: &Rig, bone: usize, b: M) {
        let p = rig.parents[bone];
        let parent = if p < 0 {
            M::identity()
        } else {
            self.global[p as usize].b.ortho()
        };
        self.set_q(bone, parent.inverse().mul(b).rotation());
        self.fk(rig);
    }
    fn aim(&mut self, rig: &Rig, bone: usize, child: usize, target: V) {
        let start = self.global[bone];
        let before = self.global[child].p.sub(start.p);
        let after = target.sub(start.p);
        if before.len2() < 1e-10 || after.len2() < 1e-10 {
            return;
        }
        self.set_basis(
            rig,
            bone,
            M::quat(Q::arc(before.unit(), after.unit())).mul(start.b.ortho()),
        );
    }
    fn solve_limb(&mut self, rig: &Rig, slot: usize, target: V, pole: V) {
        let u = self.bones[slot];
        let l = self.bones[slot + 1];
        let e = self.bones[slot + 2];
        let a = self.global[u].p;
        let b = self.global[l].p;
        let c = self.global[e].p;
        let first = a.sub(b).len();
        let second = b.sub(c).len();
        let d = target.sub(a).unit();
        let reach = a
            .sub(target)
            .len()
            .clamp((first - second).abs() + 0.0001, first + second - 0.0001);
        let along = (first * first + reach * reach - second * second) / (2. * reach);
        let mut bend = pole.sub(a).sub(d.mul(d.dot(pole.sub(a))));
        if bend.len2() < 1e-8 {
            bend = d.cross(V(1., 0., 0.));
        }
        let elbow = a.add(d.mul(along)).add(
            bend.unit()
                .mul((first * first - along * along).max(0.).sqrt()),
        );
        self.aim(rig, u, l, elbow);
        self.aim(rig, l, e, a.add(d.mul(reach)));
    }
    fn target(&self, seat: A, offset: usize, sign: f64) -> V {
        let v = &self.constants[81 + offset..];
        seat.p.add(seat.b.ortho().vec(V(v[0] * sign, v[1], v[2])))
    }
    pub fn solve(
        &mut self,
        rig: &Rig,
        gait: i64,
        sample: &[f64],
        out: &mut Vec<f64>,
    ) -> Result<(), i32> {
        if sample.len() != SAMPLE
            || !(0..4).contains(&gait)
            || !sample.iter().all(|x| x.is_finite())
            || sample[13] <= 0.
            || A::read(sample).b.det().abs() < 1e-12
        {
            return Err(INVALID);
        }
        let seat = A::read(sample);
        let actor_basis = seat.b.ortho().mul(M::quat(Q::axis(V(0., 1., 0.), PI)));
        let frame = A {
            b: actor_basis,
            p: seat.p.sub(actor_basis.vec(V::read(&self.constants))),
        };
        let visual = frame.mul(A::read(&self.constants[3..]));
        let skeleton = visual.mul(A::read(&self.constants[15..]));
        if skeleton.b.det().abs() < 1e-12 {
            return Err(INVALID);
        }
        let to_local = skeleton.inverse();
        let skeleton_basis = skeleton.b.ortho();
        self.reset(rig);
        self.fk(rig);
        let lean = self.constants[81].to_radians();
        let pelvis = self.bones[0];
        self.set_basis(
            rig,
            pelvis,
            M::quat(Q::axis(V(1., 0., 0.), lean)).mul(self.global[pelvis].b.ortho()),
        );
        let spine = self.bones[1];
        let current = skeleton_basis.mul(self.global[spine].b.ortho());
        let upright = M::quat(Q::axis(
            V(0., 1., 0.),
            actor_basis.2.0.atan2(actor_basis.2.2),
        ));
        let stabilized = upright.mul(actor_basis.inverse()).mul(current);
        let target = M::quat(
            current
                .rotation()
                .slerp(stabilized.rotation(), self.constants[82]),
        );
        self.set_basis(rig, spine, skeleton_basis.inverse().mul(target));
        for i in 0..self.thumbs.len() {
            let (b, q) = self.thumbs[i];
            self.set_q(b, self.rotations[b].slerp(q, self.constants[83]));
        }
        self.fk(rig);
        let mut grip = [M::identity(); 2];
        // Both preliminary arm solves precede motion and all leg/arm final solves.
        for (side, basis) in grip.iter_mut().enumerate() {
            let sign = if side == 0 { 1. } else { -1. };
            let s = 2 + side * 18;
            self.solve_limb(
                rig,
                s + 3,
                to_local.point(self.target(seat, 7, sign)),
                to_local.point(self.target(seat, 10, sign)),
            );
            *basis = skeleton_basis.mul(self.global[self.bones[s + 5]].b.ortho());
        }
        let phase = TAU * sample[12].rem_euclid(sample[13]) / sample[13];
        let tuning = 101 + gait as usize * 3;
        let weight = self.constants[100];
        let h = self.constants[tuning] * weight;
        let e = self.constants[tuning + 1] * weight;
        let beat = phase * self.constants[tuning + 2];
        let motion = [
            h * (beat - 0.95).sin(),
            h * 0.35 * (beat - 0.65).sin(),
            h * 0.12 * phase.sin(),
            e * 0.30 * (beat - 0.9).sin(),
            e * 0.35 * (beat - 0.75).sin(),
            e * (beat - 0.8).sin(),
        ];
        let mut targets = [V::default(); 4];
        let sf = seat.b.ortho();
        for (side, &wrist_base) in grip.iter().enumerate() {
            let sign = if side == 0 { 1. } else { -1. };
            let s = 2 + side * 18;
            let foot = self.target(seat, 13, sign);
            let knee = self.target(seat, 16, sign);
            let hand =
                self.target(seat, 7, sign)
                    .add(sf.vec(V(sign * motion[2], motion[1], motion[0])));
            let elbow =
                self.target(seat, 10, sign)
                    .add(sf.vec(V(sign * motion[3], motion[4], motion[5])));
            self.solve_limb(rig, s, to_local.point(foot), to_local.point(knee));
            self.solve_limb(rig, s + 3, to_local.point(hand), to_local.point(elbow));
            let foot_basis = M::quat(Q::axis(
                V(0., 1., 0.),
                sign * self.constants[87].to_radians(),
            ))
            .mul(M::read(&self.constants[27 + side * 9..]));
            self.set_basis(rig, self.bones[s + 2], foot_basis);
            let direction = wrist_base
                .vec(V::read(&self.constants[45 + side * 3..]))
                .unit();
            let palm = wrist_base
                .vec(V::read(&self.constants[51 + side * 3..]))
                .unit();
            let inward = sf.0.mul(-sign);
            let inward = inward.sub(direction.mul(inward.dot(direction))).unit();
            let cross = palm.cross(inward);
            let angle = cross.len().atan2(palm.dot(inward))
                * if cross.dot(direction) < 0. { -1. } else { 1. };
            let wrist = M::quat(Q::axis(direction, angle)).mul(wrist_base);
            self.set_basis(rig, self.bones[s + 5], skeleton_basis.inverse().mul(wrist));
            let hand_basis = self.global[self.bones[s + 5]].b.ortho();
            for finger in 0..4 {
                let axis = hand_basis
                    .vec(V::read(&self.constants[57 + side * 12 + finger * 3..]))
                    .unit();
                for joint in 0..3 {
                    let bone = self.bones[s + 6 + finger * 3 + joint];
                    let turn = M::quat(Q::axis(axis, self.constants[84 + joint].to_radians()));
                    self.set_basis(rig, bone, turn.mul(self.global[bone].b.ortho()));
                }
            }
            targets[side * 2] = foot;
            targets[side * 2 + 1] = hand;
        }
        // Reusable packed output: visual affine, complete local TRS, then five
        // world-space contact errors. Publish only if every number is finite.
        let start = out.len();
        visual.write(out);
        for i in 0..self.local.len() {
            self.local[i].p.write(out);
            self.rotations[i].write(out);
            self.scales[i].write(out);
        }
        for side in 0..2 {
            let s = 2 + side * 18;
            for (k, b) in [s + 2, s + 5].iter().enumerate() {
                out.push(
                    skeleton
                        .point(self.global[self.bones[*b]].p)
                        .sub(targets[side * 2 + k])
                        .len(),
                );
            }
        }
        out.push(skeleton.point(self.global[pelvis].p).sub(seat.p).len());
        if !out[start..].iter().all(|x| x.is_finite()) {
            out.truncate(start);
            return Err(INVALID);
        }
        Ok(())
    }
}

#[cfg(test)]
pub(crate) mod tests {
    use super::*;
    pub(crate) fn fixture() -> (Rig, Vec<i32>, Vec<f64>) {
        let mut parents = vec![-1; 38];
        let mut pose = vec![0.; 380];
        for i in 0..38 {
            pose[i * 10 + 6] = 1.;
            pose[i * 10 + 7..i * 10 + 10].fill(1.);
        }
        parents[1] = 0;
        pose[1] = 1.;
        pose[11] = 0.3;
        for side in 0..2 {
            let s = 2 + side * 18;
            let sign = if side == 0 { 1. } else { -1. };
            for (k, p) in [0, s, s + 1, 1, s + 3, s + 4].iter().enumerate() {
                parents[s + k] = *p as i32;
            }
            let positions = [
                V(0.2 * sign, -0.05, 0.),
                V(0., -0.4, 0.),
                V(0., -0.4, 0.1),
                V(0.25 * sign, 0.25, 0.),
                V(0.3 * sign, 0., 0.),
                V(0.3 * sign, 0., 0.),
            ];
            for (k, p) in positions.iter().enumerate() {
                pose[(s + k) * 10..(s + k) * 10 + 3].copy_from_slice(&[p.0, p.1, p.2]);
            }
            for finger in 0..4 {
                for joint in 0..3 {
                    let i = s + 6 + finger * 3 + joint;
                    parents[i] = if joint == 0 {
                        (s + 5) as i32
                    } else {
                        (i - 1) as i32
                    };
                    pose[i * 10 + 2] = if joint == 0 { 0.07 } else { 0.03 };
                    pose[i * 10] = if joint == 0 {
                        (finger as f64 - 1.5) * 0.025
                    } else {
                        0.
                    };
                }
            }
        }
        let mut constants = Vec::new();
        V(0., 1., 0.).write(&mut constants);
        A::identity().write(&mut constants);
        A::identity().write(&mut constants);
        M::identity().write(&mut constants);
        M::identity().write(&mut constants);
        for _ in 0..2 {
            V(0., 0., 1.).write(&mut constants);
        }
        for _ in 0..2 {
            V(0., 1., 0.).write(&mut constants);
        }
        for _ in 0..8 {
            V(1., 0., 0.).write(&mut constants);
        }
        constants.extend([
            3., 0.55, 0.95, 55., 70., 50., 8., 0.3, 0.3, 0.35, 0.5, 0.15, -0.1, 0.3, -0.75, 0.,
            0.4, -0.3, 0.4, 1.,
        ]);
        constants.extend([
            0.02, 0.02, 1., 0.03, 0.04, 1., 0.02, 0.03, 2., 0.04, 0.05, 1.,
        ]);
        let mut rest = Vec::new();
        for _ in 0..38 {
            A::identity().write(&mut rest);
        }
        (
            Rig {
                parents,
                rest,
                neutral_pose: pose,
            },
            (0..38).collect(),
            constants,
        )
    }
    #[test]
    fn solves_from_neutral_without_history_or_rest_double_composition() {
        let (rig, bones, constants) = fixture();
        let mut rider = Rider::new(1, &rig, &bones, &constants, &[], &[]).unwrap();
        let seat = A {
            b: M::quat(Q::axis(V(0., 1., 0.), 0.7)),
            p: V(10., 2., -5.),
        };
        let mut sample = Vec::new();
        seat.write(&mut sample);
        sample.extend([0., 1.]);
        for gait in 0..4 {
            for clock in [0., -2., 0.125, 1e12] {
                sample[12] = clock;
                let mut first = Vec::new();
                rider.solve(&rig, gait, &sample, &mut first).unwrap();
                let mut second = Vec::new();
                rider.solve(&rig, gait, &sample, &mut second).unwrap();
                assert_eq!(first.len(), 397);
                assert_eq!(first, second);
                assert!(first.iter().all(|x| x.is_finite()));
                let mut other = rig.clone();
                other.rest.fill(17.);
                let mut output = Vec::new();
                rider.solve(&other, gait, &sample, &mut output).unwrap();
                assert_eq!(first, output);
            }
        }
    }
    #[test]
    fn invalid_sample_does_not_publish_partial_output() {
        let (rig, bones, constants) = fixture();
        let mut rider = Rider::new(1, &rig, &bones, &constants, &[], &[]).unwrap();
        let mut sample = Vec::new();
        A::identity().write(&mut sample);
        sample.extend([0., 0.]);
        let mut output = vec![123.];
        assert_eq!(rider.solve(&rig, 0, &sample, &mut output), Err(INVALID));
        assert_eq!(output, vec![123.]);
        sample[13] = 1.;
        sample[0] = f64::NAN;
        assert_eq!(rider.solve(&rig, 0, &sample, &mut output), Err(INVALID));
        assert_eq!(output, vec![123.]);
    }
    #[test]
    fn affine_inverse_preserves_scaled_rotated_translated_points() {
        let r = M::quat(Q::axis(V(0., 1., 0.), 1.3));
        let a = A {
            b: M(r.0.mul(2.), r.1.mul(3.), r.2.mul(4.)),
            p: V(7., -3., 99.),
        };
        let p = V(-9., 2., 3.);
        assert!(a.inverse().point(a.point(p)).sub(p).len() < 1e-11);
    }
    #[test]
    fn quaternion_sign_and_rotation_matrix_roundtrip() {
        for axis in [
            V(1., 0., 0.),
            V(0., 1., 0.),
            V(0., 0., 1.),
            V(1., 2., 3.).unit(),
        ] {
            for angle in [0., 0.1, PI, 4.5] {
                let q = Q::axis(axis, angle);
                assert!((q.dot(M::quat(q).rotation()).abs() - 1.).abs() < 1e-12);
            }
        }
    }
}
