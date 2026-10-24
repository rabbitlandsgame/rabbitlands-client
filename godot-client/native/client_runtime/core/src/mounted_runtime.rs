//! Additive mounted pilot API; Phase 4 scheduling ABI remains unchanged.
use crate::mounted_pose::{BONE_SLOTS, CONSTANTS, MAX_RIDERS, Rider, SAMPLE};
use crate::*;

#[repr(C)]
#[derive(Clone, Copy, Debug, Default)]
pub struct MountedRecord {
    pub id: i64,
    pub generation: i64,
    pub rider: u64,
    pub gait: i64,
    pub frame: i64,
}
#[repr(C)]
#[derive(Clone, Copy, Debug, Default)]
pub struct MountedResult {
    pub id: i64,
    pub generation: i64,
    pub epoch: i64,
    pub frame: i64,
    pub offset: u64,
    pub bones: u64,
}

impl Runtime {
    pub fn register_mounted_rider(
        &mut self,
        rig_handle: u64,
        bones: &[i32],
        constants: &[f64],
        thumbs: &[i32],
        grips: &[f64],
    ) -> Result<u64, i32> {
        if self.mounted_riders.len() >= MAX_RIDERS || self.next_handle == u64::MAX {
            return Err(INVALID);
        }
        let rig = &self
            .rigs
            .iter()
            .find(|(h, _)| *h == rig_handle)
            .ok_or(STALE)?
            .1;
        let rider = Rider::new(rig_handle, rig, bones, constants, thumbs, grips)?;
        let handle = self.next_handle;
        self.next_handle += 1;
        self.mounted_riders.push((handle, rider));
        Ok(handle)
    }
    pub fn unregister_mounted_rider(&mut self, handle: u64) -> Result<(), i32> {
        let index = self
            .mounted_riders
            .iter()
            .position(|(h, _)| *h == handle)
            .ok_or(STALE)?;
        self.mounted_riders.swap_remove(index);
        Ok(())
    }
    pub fn set_mounted_lean(&mut self, handle: u64, degrees: f64) -> Result<(), i32> {
        self.mounted_riders.iter_mut().find(|(h, _)| *h == handle)
            .ok_or(STALE)?.1.set_lean(degrees)
    }
    pub fn solve_mounted(
        &mut self,
        records: &[MountedRecord],
        samples: &[f64],
        epoch: i64,
    ) -> Result<(), i32> {
        if epoch != self.epoch {
            return Err(STALE);
        }
        if records.len() > MAX_RIDERS || samples.len() != records.len() * SAMPLE {
            return Err(INVALID);
        }
        let mut required = 0usize;
        for (i, row) in records.iter().enumerate() {
            if row.id < 0
                || row.generation <= 0
                || row.frame < 0
                || !(0..4).contains(&row.gait)
                || records[..i]
                    .iter()
                    .any(|r| r.rider == row.rider || r.id == row.id)
            {
                return Err(INVALID);
            }
            let rider = &self
                .mounted_riders
                .iter()
                .find(|(h, _)| *h == row.rider)
                .ok_or(STALE)?
                .1;
            let rig = &self
                .rigs
                .iter()
                .find(|(h, _)| *h == rider.rig)
                .ok_or(STALE)?
                .1;
            required = required
                .checked_add(17 + rig.parents.len() * 10)
                .ok_or(INVALID)?;
        }
        if required > 8_388_608 || !samples.iter().all(|x| x.is_finite()) {
            return Err(INVALID);
        }
        self.mounted_values.clear();
        self.mounted_results.clear();
        self.mounted_values.reserve(required);
        for (i, row) in records.iter().enumerate() {
            let rider = &mut self
                .mounted_riders
                .iter_mut()
                .find(|(h, _)| *h == row.rider)
                .ok_or(STALE)?
                .1;
            let rig = &self
                .rigs
                .iter()
                .find(|(h, _)| *h == rider.rig)
                .ok_or(STALE)?
                .1;
            let offset = self.mounted_values.len() as u64;
            rider.solve(
                rig,
                row.gait,
                &samples[i * SAMPLE..(i + 1) * SAMPLE],
                &mut self.mounted_values,
            )?;
            self.mounted_results.push(MountedResult {
                id: row.id,
                generation: row.generation,
                epoch,
                frame: row.frame,
                offset,
                bones: rig.parents.len() as u64,
            });
        }
        Ok(())
    }
}

#[unsafe(no_mangle)]
pub unsafe extern "C" fn rl_client_runtime_register_mounted_rider(
    runtime: *mut Runtime,
    rig: u64,
    bones: *const i32,
    constants: *const f64,
    thumbs: *const i32,
    grips: *const f64,
    thumb_count: usize,
    output: *mut u64,
) -> i32 {
    if runtime.is_null()
        || bones.is_null()
        || constants.is_null()
        || output.is_null()
        || thumb_count > MAX_BONES
        || (thumb_count != 0 && (thumbs.is_null() || grips.is_null()))
    {
        return INVALID;
    }
    catch_unwind(AssertUnwindSafe(|| unsafe {
        let t = if thumb_count == 0 {
            &[]
        } else {
            std::slice::from_raw_parts(thumbs, thumb_count)
        };
        let q = if thumb_count == 0 {
            &[]
        } else {
            std::slice::from_raw_parts(grips, thumb_count * 4)
        };
        match (&mut *runtime).register_mounted_rider(
            rig,
            std::slice::from_raw_parts(bones, BONE_SLOTS),
            std::slice::from_raw_parts(constants, CONSTANTS),
            t,
            q,
        ) {
            Ok(handle) => {
                *output = handle;
                OK
            }
            Err(e) => e,
        }
    }))
    .unwrap_or(INTERNAL)
}
#[unsafe(no_mangle)]
pub unsafe extern "C" fn rl_client_runtime_unregister_mounted_rider(
    runtime: *mut Runtime,
    handle: u64,
) -> i32 {
    if runtime.is_null() {
        return INVALID;
    }
    catch_unwind(AssertUnwindSafe(|| unsafe {
        (&mut *runtime)
            .unregister_mounted_rider(handle)
            .err()
            .unwrap_or(OK)
    }))
    .unwrap_or(INTERNAL)
}
#[unsafe(no_mangle)]
pub unsafe extern "C" fn rl_client_runtime_set_mounted_lean(
    runtime: *mut Runtime, handle: u64, degrees: f64,
) -> i32 {
    if runtime.is_null() { return INVALID; }
    catch_unwind(AssertUnwindSafe(|| unsafe {
        (&mut *runtime).set_mounted_lean(handle, degrees).err().unwrap_or(OK)
    })).unwrap_or(INTERNAL)
}
#[unsafe(no_mangle)]
pub unsafe extern "C" fn rl_client_runtime_solve_mounted(
    runtime: *mut Runtime,
    records: *const MountedRecord,
    samples: *const f64,
    count: usize,
    epoch: i64,
    output: *mut MountedResult,
    output_capacity: usize,
    values: *mut f64,
    value_capacity: usize,
    value_count: *mut usize,
) -> i32 {
    if runtime.is_null()
        || count > MAX_RIDERS
        || output_capacity < count
        || value_count.is_null()
        || (count != 0
            && (records.is_null() || samples.is_null() || output.is_null() || values.is_null()))
    {
        return INVALID;
    }
    catch_unwind(AssertUnwindSafe(|| unsafe {
        let rows = if count == 0 {
            &[]
        } else {
            std::slice::from_raw_parts(records, count)
        };
        let input = if count == 0 {
            &[]
        } else {
            std::slice::from_raw_parts(samples, count * SAMPLE)
        };
        let core = &mut *runtime;
        match core.solve_mounted(rows, input, epoch) {
            Err(e) => e,
            Ok(()) => {
                if core.mounted_values.len() > value_capacity {
                    return INVALID;
                }
                if count != 0 {
                    std::ptr::copy_nonoverlapping(core.mounted_results.as_ptr(), output, count);
                    std::ptr::copy_nonoverlapping(
                        core.mounted_values.as_ptr(),
                        values,
                        core.mounted_values.len(),
                    );
                }
                *value_count = core.mounted_values.len();
                OK
            }
        }
    }))
    .unwrap_or(INTERNAL)
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn whole_batch_validation_and_epoch_reset_preserve_caller_buffers() {
        let (source, bones, constants) = crate::mounted_pose::tests::fixture();
        let mut runtime = Runtime::default();
        let rig = runtime
            .register_rig(&source.parents, &source.rest, &source.neutral_pose)
            .unwrap();
        let rider = runtime
            .register_mounted_rider(rig, &bones, &constants, &[], &[])
            .unwrap();
        let mut samples = vec![0.; 28];
        for offset in [0, 14] {
            for i in [0, 4, 8] {
                samples[offset + i] = 1.;
            }
            samples[offset + 13] = 1.;
        }
        let records = [
            MountedRecord {
                id: 1,
                generation: 2,
                rider,
                gait: 0,
                frame: 1,
            },
            MountedRecord {
                id: 2,
                generation: 2,
                rider,
                gait: 9,
                frame: 1,
            },
        ];
        let mut metadata = [MountedResult {
            id: 77,
            ..MountedResult::default()
        }; 2];
        let mut values = vec![123.; 794];
        let mut count = 99;
        assert_eq!(
            unsafe {
                rl_client_runtime_solve_mounted(
                    &mut runtime,
                    records.as_ptr(),
                    samples.as_ptr(),
                    2,
                    1,
                    metadata.as_mut_ptr(),
                    2,
                    values.as_mut_ptr(),
                    values.len(),
                    &mut count,
                )
            },
            INVALID
        );
        assert_eq!(metadata[0].id, 77);
        assert_eq!(metadata[1].id, 77);
        assert_eq!(count, 99);
        assert!(values.iter().all(|x| *x == 123.));
        let row = [MountedRecord {
            id: 1,
            generation: 2,
            rider,
            gait: 0,
            frame: 1,
        }];
        runtime.reset(2).unwrap();
        assert_eq!(runtime.solve_mounted(&row, &samples[..14], 2), Err(STALE));
        assert_eq!(runtime.solve_mounted(&row, &samples[..14], 1), Err(STALE));
    }
    #[test]
    fn gait_lean_event_is_finite_and_generation_scoped() {
        let (source, bones, constants) = crate::mounted_pose::tests::fixture();
        let mut runtime = Runtime::default();
        let rig = runtime.register_rig(&source.parents, &source.rest, &source.neutral_pose).unwrap();
        let rider = runtime.register_mounted_rider(rig, &bones, &constants, &[], &[]).unwrap();
        let rows = [MountedRecord { id: 1, generation: 2, rider, gait: 3, frame: 1 }];
        let mut samples = [0.; SAMPLE];
        for i in [0,4,8] { samples[i]=1.; }
        samples[13]=1.;
        runtime.solve_mounted(&rows,&samples,1).unwrap();
        let baseline=runtime.mounted_values.clone();
        runtime.set_mounted_lean(rider, constants[81]+7.).unwrap();
        runtime.solve_mounted(&rows,&samples,1).unwrap();
        let changed=runtime.mounted_values.clone();
        assert_ne!(baseline,changed);
        assert_eq!(runtime.set_mounted_lean(rider,f64::NAN),Err(INVALID));
        assert_eq!(runtime.set_mounted_lean(rider,f64::INFINITY),Err(INVALID));
        runtime.solve_mounted(&rows,&samples,1).unwrap();
        assert_eq!(runtime.mounted_values,changed);
        runtime.reset(2).unwrap();
        assert_eq!(runtime.set_mounted_lean(rider,1.),Err(STALE));
    }

}
