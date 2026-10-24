//! Additive ABI surface. Trusted owner-thread adapter supplies aligned, live,
//! nonaliasing buffers, as for the existing animation planner ABI.
use std::panic::{AssertUnwindSafe, catch_unwind};
use crate::{Runtime, OK, INVALID, INTERNAL, residency::*};

unsafe fn values<'a,T>(pointer:*const T,count:usize)->&'a [T] {
    if count==0 { &[] } else { unsafe { std::slice::from_raw_parts(pointer,count) } }
}

#[unsafe(no_mangle)]
pub extern "C" fn rl_client_runtime_residency_schema()->u32 { 1 }

#[unsafe(no_mangle)]
pub unsafe extern "C" fn rl_client_runtime_residency_catalog(runtime:*mut Runtime,
    descriptors:*const Descriptor,count:usize,dependencies:*const Key,dependency_count:usize)->i32 {
    if runtime.is_null() || count>MAX_CATALOG || dependency_count>MAX_DEPENDENCIES
        || (count!=0&&descriptors.is_null()) || (dependency_count!=0&&dependencies.is_null()) { return INVALID; }
    catch_unwind(AssertUnwindSafe(|| unsafe {
        (&mut *runtime).residency.set_catalog(values(descriptors,count),values(dependencies,dependency_count)).err().unwrap_or(OK)
    })).unwrap_or(INTERNAL)
}

#[unsafe(no_mangle)]
pub unsafe extern "C" fn rl_client_runtime_residency_reconcile(runtime:*mut Runtime,
    wanted:*const Wanted,count:usize,epoch:i64)->i32 {
    if runtime.is_null() || count>MAX_CATALOG || (count!=0&&wanted.is_null()) { return INVALID; }
    catch_unwind(AssertUnwindSafe(|| unsafe {
        (&mut *runtime).residency.reconcile(epoch,values(wanted,count)).err().unwrap_or(OK)
    })).unwrap_or(INTERNAL)
}

#[unsafe(no_mangle)]
pub unsafe extern "C" fn rl_client_runtime_residency_events(runtime:*mut Runtime,
    events:*const Event,count:usize)->i32 {
    if runtime.is_null() || count>MAX_CATALOG || (count!=0&&events.is_null()) { return INVALID; }
    catch_unwind(AssertUnwindSafe(|| unsafe {
        (&mut *runtime).residency.events(values(events,count)).err().unwrap_or(OK)
    })).unwrap_or(INTERNAL)
}

#[unsafe(no_mangle)]
pub unsafe extern "C" fn rl_client_runtime_residency_retry(runtime:*mut Runtime,
    keys:*const Key,count:usize,epoch:i64)->i32 {
    if runtime.is_null() || count>MAX_CATALOG || (count!=0&&keys.is_null()) { return INVALID; }
    catch_unwind(AssertUnwindSafe(|| unsafe {
        (&mut *runtime).residency.retry_failed(epoch,values(keys,count)).err().unwrap_or(OK)
    })).unwrap_or(INTERNAL)
}

#[unsafe(no_mangle)]
pub unsafe extern "C" fn rl_client_runtime_residency_step(runtime:*mut Runtime,epoch:i64,
    budget:Budget,output:*mut Action,capacity:usize,written:*mut usize)->i32 {
    if runtime.is_null() || written.is_null() || capacity>MAX_ACTIONS
        || (capacity!=0&&output.is_null()) { return INVALID; }
    catch_unwind(AssertUnwindSafe(|| unsafe {
        match (&mut *runtime).residency.step(epoch,budget,capacity) {
            Ok(actions)=>{
                if !actions.is_empty() { std::ptr::copy_nonoverlapping(actions.as_ptr(),output,actions.len()); }
                *written=actions.len(); OK
            },
            Err(error)=>error,
        }
    })).unwrap_or(INTERNAL)
}

#[unsafe(no_mangle)]
pub unsafe extern "C" fn rl_client_runtime_residency_snapshot(runtime:*const Runtime,
    budget:Budget,output:*mut Snapshot)->i32 {
    if runtime.is_null() || output.is_null() { return INVALID; }
    catch_unwind(AssertUnwindSafe(|| unsafe {
        *output=(&*runtime).residency.snapshot(budget); OK
    })).unwrap_or(INTERNAL)
}

#[unsafe(no_mangle)]
pub unsafe extern "C" fn rl_client_runtime_admission_begin(runtime:*mut Runtime,epoch:i64,
    input:crate::admission::Input,output:*mut crate::admission::Decision)->i32 {
    if runtime.is_null() || output.is_null() {return INVALID;}
    catch_unwind(AssertUnwindSafe(|| unsafe {
        let owner=&mut *runtime;
        match owner.admission.begin(owner.epoch,epoch,input) {
            Ok(decision)=>{*output=decision;OK},Err(error)=>error,
        }
    })).unwrap_or(INTERNAL)
}
#[unsafe(no_mangle)]
pub unsafe extern "C" fn rl_client_runtime_admission_event(runtime:*mut Runtime,id:u64,epoch:i64,event:i64)->i32 {
    if runtime.is_null() {return INVALID;}
    catch_unwind(AssertUnwindSafe(|| unsafe {
        let owner=&mut *runtime;owner.admission.event(owner.epoch,id,epoch,event).err().unwrap_or(OK)
    })).unwrap_or(INTERNAL)
}
#[unsafe(no_mangle)]
pub unsafe extern "C" fn rl_client_runtime_admission_snapshot(runtime:*const Runtime,
    output:*mut crate::admission::Snapshot)->i32 {
    if runtime.is_null() || output.is_null() {return INVALID;}
    catch_unwind(AssertUnwindSafe(|| unsafe {
        let owner=&*runtime;*output=owner.admission.snapshot(owner.epoch);OK
    })).unwrap_or(INTERNAL)
}

#[unsafe(no_mangle)]
pub unsafe extern "C" fn rl_client_runtime_admission_dependencies(runtime:*mut Runtime,id:u64,epoch:i64,
    records:*const Descriptor,count:usize,edges:*const Key,edge_count:usize)->i32 {
    if runtime.is_null() || count>MAX_CATALOG || edge_count>MAX_DEPENDENCIES
        || (count!=0&&records.is_null()) || (edge_count!=0&&edges.is_null()) {return INVALID;}
    catch_unwind(AssertUnwindSafe(|| unsafe {
        (&mut *runtime).admission.bind_dependencies(id,epoch,values(records,count),values(edges,edge_count)).err().unwrap_or(OK)
    })).unwrap_or(INTERNAL)
}
#[unsafe(no_mangle)]
pub unsafe extern "C" fn rl_client_runtime_admission_release_dependencies(runtime:*mut Runtime,
    keys:*const Key,count:usize,output:*mut Key,capacity:usize,written:*mut usize)->i32 {
    if runtime.is_null() || written.is_null() || count>MAX_CATALOG || capacity<count
        || (count!=0&&(keys.is_null()||output.is_null())) {return INVALID;}
    catch_unwind(AssertUnwindSafe(|| unsafe {
        match (&mut *runtime).admission.release_dependencies(values(keys,count)) {
            Ok(removed)=>{
                if !removed.is_empty() {std::ptr::copy_nonoverlapping(removed.as_ptr(),output,removed.len());}
                *written=removed.len();OK
            },Err(error)=>error,
        }
    })).unwrap_or(INTERNAL)
}
#[unsafe(no_mangle)]
pub unsafe extern "C" fn rl_client_runtime_admission_graph_snapshot(runtime:*const Runtime,
    output:*mut crate::admission::GraphSnapshot)->i32 {
    if runtime.is_null() || output.is_null() {return INVALID;}
    catch_unwind(AssertUnwindSafe(|| unsafe {
        *output=(&*runtime).admission.graph_snapshot();OK
    })).unwrap_or(INTERNAL)
}
