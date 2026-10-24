//! Engine-independent, main-thread-owned presentation data. No Godot pointers.
pub mod flight;

use std::panic::{AssertUnwindSafe, catch_unwind};
mod mounted_pose;
mod mounted_runtime;
use mounted_pose::Rider;
use mounted_runtime::MountedResult;

pub const ABI_VERSION: u32 = 1;
pub const OK: i32 = 0;
pub const INVALID: i32 = 1;
pub const STALE: i32 = 2;
pub const INTERNAL: i32 = 3;
const MAX_RECORDS: usize = 65_536;
const MAX_BONES: usize = 1_024;

#[repr(C)]
#[derive(Clone, Copy, Debug, Default)]
pub struct PlanRecord {
    pub id: i64,
    pub generation: i64,
    pub rig: u64,
    pub tier: i64,
    pub phase: i64,
}

#[repr(C)]
#[derive(Clone, Copy, Debug, Default, PartialEq)]
pub struct PlanResult {
    pub id: i64,
    pub generation: i64,
    pub epoch: i64,
    pub due: i64,
}

#[derive(Clone)]
pub struct Rig {
    pub parents: Vec<i32>,
    /// Column-major affine: basis X/Y/Z then origin, twelve f64 per bone.
    pub rest: Vec<f64>,
    /// Parent-local pose: position XYZ, quaternion XYZW, scale XYZ.
    pub neutral_pose: Vec<f64>,
}

pub struct Runtime {
    epoch: i64,
    next_handle: u64,
    rigs: Vec<(u64, Rig)>,
    scratch: Vec<PlanResult>,
    mounted_riders: Vec<(u64, Rider)>,
    mounted_values: Vec<f64>,
    mounted_results: Vec<MountedResult>,
}

impl Default for Runtime {
    fn default() -> Self {
        Self {
            epoch: 1,
            next_handle: 1,
            rigs: Vec::new(),
            scratch: Vec::new(),
            mounted_riders: Vec::new(),
            mounted_values: Vec::new(),
            mounted_results: Vec::new(),
        }
    }
}

impl Runtime {
    pub fn reset(&mut self, epoch: i64) -> Result<(), i32> {
        if epoch <= self.epoch {
            return Err(STALE);
        }
        self.epoch = epoch;
        self.rigs.clear();
        self.scratch.clear();
        self.mounted_riders.clear();
        self.mounted_values.clear();
        self.mounted_results.clear();
        // Handles are never reused, including after a map/session reset.
        Ok(())
    }

    pub fn register_rig(
        &mut self,
        parents: &[i32],
        rest: &[f64],
        pose: &[f64],
    ) -> Result<u64, i32> {
        let count = parents.len();
        if count == 0
            || count > MAX_BONES
            || rest.len() != count * 12
            || pose.len() != count * 10
            || !rest.iter().chain(pose.iter()).all(|x| x.is_finite())
        {
            return Err(INVALID);
        }
        for bone in 0..count {
            let mut parent = parents[bone];
            let mut steps = 0;
            while parent != -1 {
                if parent < 0
                    || parent as usize >= count
                    || parent as usize == bone
                    || steps >= count
                {
                    return Err(INVALID);
                }
                parent = parents[parent as usize];
                steps += 1;
            }
            let q = &pose[bone * 10 + 3..bone * 10 + 7];
            if q.iter().map(|x| x * x).sum::<f64>() < 1e-12 {
                return Err(INVALID);
            }
        }
        if self.next_handle == u64::MAX {
            return Err(INTERNAL);
        }
        let handle = self.next_handle;
        self.next_handle += 1;
        self.rigs.push((
            handle,
            Rig {
                parents: parents.to_vec(),
                rest: rest.to_vec(),
                neutral_pose: pose.to_vec(),
            },
        ));
        Ok(handle)
    }

    pub fn unregister_rig(&mut self, handle: u64) -> bool {
        if let Some(index) = self.rigs.iter().position(|(id, _)| *id == handle) {
            self.rigs.swap_remove(index);
            self.mounted_riders.retain(|(_, rider)| rider.rig != handle);
            true
        } else {
            false
        }
    }

    pub fn plan(
        &mut self,
        records: &[PlanRecord],
        epoch: i64,
        tick: i64,
    ) -> Result<&[PlanResult], i32> {
        if epoch != self.epoch {
            return Err(STALE);
        }
        if tick < 0 || records.len() > MAX_RECORDS {
            return Err(INVALID);
        }
        // Validate the complete batch before changing output/scratch state.
        for record in records {
            let stride = match record.tier {
                0 | 2 => 1,
                1 => 2,
                3 => 4,
                _ => return Err(INVALID),
            };
            if record.id < 0 || record.generation <= 0 || record.phase < 0 || record.phase >= stride
            {
                return Err(INVALID);
            }
            if record.rig != 0 && !self.rigs.iter().any(|(handle, _)| *handle == record.rig) {
                return Err(STALE);
            }
        }
        self.scratch.clear();
        self.scratch.extend(records.iter().map(|record| {
            let due = match record.tier {
                0 => true,
                2 => false,
                1 => (tick % 2 + record.phase) % 2 == 0,
                3 => (tick % 4 + record.phase) % 4 == 0,
                _ => unreachable!(),
            };
            PlanResult {
                id: record.id,
                generation: record.generation,
                epoch,
                due: i64::from(due),
            }
        }));
        Ok(&self.scratch)
    }
}

#[unsafe(no_mangle)]
pub extern "C" fn rl_client_runtime_abi() -> u32 {
    ABI_VERSION
}

#[unsafe(no_mangle)]
pub extern "C" fn rl_client_runtime_create() -> *mut Runtime {
    catch_unwind(|| Box::into_raw(Box::new(Runtime::default()))).unwrap_or(std::ptr::null_mut())
}

/// All FFI pointers originate in the trusted adapter, are aligned/live and do
/// not alias. Field errors are recoverable; arbitrary corrupt pointers are not.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn rl_client_runtime_destroy(runtime: *mut Runtime) {
    if !runtime.is_null() {
        let _ = catch_unwind(AssertUnwindSafe(|| unsafe {
            drop(Box::from_raw(runtime));
        }));
    }
}

#[unsafe(no_mangle)]
pub unsafe extern "C" fn rl_client_runtime_reset(runtime: *mut Runtime, epoch: i64) -> i32 {
    if runtime.is_null() {
        return INVALID;
    }
    catch_unwind(AssertUnwindSafe(|| unsafe {
        (&mut *runtime).reset(epoch).err().unwrap_or(OK)
    }))
    .unwrap_or(INTERNAL)
}

#[unsafe(no_mangle)]
pub unsafe extern "C" fn rl_client_runtime_register_rig(
    runtime: *mut Runtime,
    parents: *const i32,
    rest: *const f64,
    pose: *const f64,
    count: usize,
    output: *mut u64,
) -> i32 {
    if runtime.is_null()
        || parents.is_null()
        || rest.is_null()
        || pose.is_null()
        || output.is_null()
        || count == 0
        || count > MAX_BONES
    {
        return INVALID;
    }
    catch_unwind(AssertUnwindSafe(|| unsafe {
        match (&mut *runtime).register_rig(
            std::slice::from_raw_parts(parents, count),
            std::slice::from_raw_parts(rest, count * 12),
            std::slice::from_raw_parts(pose, count * 10),
        ) {
            Ok(handle) => {
                *output = handle;
                OK
            }
            Err(error) => error,
        }
    }))
    .unwrap_or(INTERNAL)
}

#[unsafe(no_mangle)]
pub unsafe extern "C" fn rl_client_runtime_unregister_rig(
    runtime: *mut Runtime,
    handle: u64,
) -> i32 {
    if runtime.is_null() {
        return INVALID;
    }
    catch_unwind(AssertUnwindSafe(|| unsafe {
        if (&mut *runtime).unregister_rig(handle) {
            OK
        } else {
            STALE
        }
    }))
    .unwrap_or(INTERNAL)
}

#[unsafe(no_mangle)]
pub unsafe extern "C" fn rl_client_runtime_plan(
    runtime: *mut Runtime,
    records: *const PlanRecord,
    count: usize,
    epoch: i64,
    tick: i64,
    output: *mut PlanResult,
    capacity: usize,
) -> i32 {
    if runtime.is_null()
        || count > MAX_RECORDS
        || capacity < count
        || (count != 0 && (records.is_null() || output.is_null()))
    {
        return INVALID;
    }
    catch_unwind(AssertUnwindSafe(|| unsafe {
        let input = if count == 0 {
            &[]
        } else {
            std::slice::from_raw_parts(records, count)
        };
        match (&mut *runtime).plan(input, epoch, tick) {
            Ok(result) => {
                if count != 0 {
                    std::ptr::copy_nonoverlapping(result.as_ptr(), output, count);
                }
                OK
            }
            Err(error) => error,
        }
    }))
    .unwrap_or(INTERNAL)
}

#[cfg(test)]
mod tests {
    use super::*;
    fn rig(runtime: &mut Runtime) -> u64 {
        runtime
            .register_rig(
                &[-1, 0],
                &[0.0; 24],
                &[
                    0., 0., 0., 0., 0., 0., 1., 1., 1., 1., 0., 0., 0., 0., 0., 0., 1., 1., 1., 1.,
                ],
            )
            .unwrap()
    }
    #[test]
    fn cadence_matches_all_groups_without_clock_overflow() {
        let mut runtime = Runtime::default();
        for tick in [0, 1, 2, 3, 4, 17, i64::MAX] {
            for (tier, stride) in [(0, 1), (1, 2), (2, 1), (3, 4)] {
                for phase in 0..stride {
                    let row = PlanRecord {
                        id: 9001,
                        generation: 7,
                        rig: 0,
                        tier,
                        phase,
                    };
                    let result = runtime.plan(&[row], 1, tick).unwrap()[0];
                    assert_eq!(
                        result.due == 1,
                        tier == 0 || (tier != 2 && (tick % stride + phase) % stride == 0)
                    );
                }
            }
        }
    }
    #[test]
    fn reset_rejects_stale_handles_and_does_not_reuse_them() {
        let mut runtime = Runtime::default();
        let old = rig(&mut runtime);
        runtime.reset(2).unwrap();
        assert_ne!(old, rig(&mut runtime));
        assert_eq!(
            runtime.plan(
                &[PlanRecord {
                    id: 1,
                    generation: 1,
                    rig: old,
                    tier: 0,
                    phase: 0
                }],
                2,
                0
            ),
            Err(STALE)
        );
        assert_eq!(runtime.reset(2), Err(STALE));
        assert_eq!(runtime.plan(&[], 1, 0), Err(STALE));
    }
    #[test]
    fn invalid_complete_batch_preserves_output() {
        let mut runtime = Runtime::default();
        let before = PlanResult {
            id: 77,
            generation: 22,
            epoch: 9,
            due: 8,
        };
        let mut out = [before; 2];
        let input = [
            PlanRecord {
                id: 1,
                generation: 1,
                rig: 0,
                tier: 0,
                phase: 0,
            },
            PlanRecord {
                id: 2,
                generation: 1,
                rig: 0,
                tier: 7,
                phase: 0,
            },
        ];
        assert_eq!(
            unsafe {
                rl_client_runtime_plan(&mut runtime, input.as_ptr(), 2, 1, 0, out.as_mut_ptr(), 2)
            },
            INVALID
        );
        assert_eq!(out, [before; 2]);
    }
    #[test]
    fn rejects_rig_cycles_nonfinite_and_invalid_lengths() {
        let mut runtime = Runtime::default();
        assert_eq!(
            runtime.register_rig(&[0], &[0.; 12], &[0.; 10]),
            Err(INVALID)
        );
        assert_eq!(
            runtime.register_rig(&[1, 0], &[0.; 24], &[0.; 20]),
            Err(INVALID)
        );
        assert_eq!(
            runtime.register_rig(&[-1], &[f64::NAN; 12], &[0.; 10]),
            Err(INVALID)
        );
        assert_eq!(
            unsafe {
                rl_client_runtime_plan(
                    std::ptr::null_mut(),
                    std::ptr::null(),
                    0,
                    1,
                    0,
                    std::ptr::null_mut(),
                    0,
                )
            },
            INVALID
        );
    }
}
