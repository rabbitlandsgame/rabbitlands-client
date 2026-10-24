//! Real-loader admission leases. Godot supplies a deduplicated phase3 snapshot
//! and remains the only owner/executor. Unknown allocation is explicit.
use std::collections::{BTreeMap,BTreeSet};
use crate::{INVALID, STALE};
use crate::residency::{Descriptor,Key,MAX_CATALOG,MAX_DEPENDENCIES};
#[repr(C)]
#[derive(Clone,Copy,Default)]
pub struct Input { pub estimated_bytes:u64,pub candidate_bytes:u64,pub budget_bytes:u64,
    pub live_workers:u64,pub maximum_workers:u64,pub retiring_roots:u64,
    pub unknown_resources:u64,pub unknown_limit:u64,pub pinned:u64,pub synchronous:u64 }
#[repr(C)]
#[derive(Clone,Copy,Default)]
pub struct Decision { pub lease:u64,pub reason:u64 }
#[repr(C)]
#[derive(Clone,Copy,Default)]
pub struct Snapshot { pub reserved:u64,pub loading:u64,pub ready:u64,pub active:u64,
    pub retiring:u64,pub cancelled:u64,pub old_epoch:u64,pub denials:u64,pub forced_sync:u64 }
#[derive(Clone,Copy,PartialEq,Eq)]
enum State { Reserved,Loading,Ready,Active,Retiring }
struct Lease { epoch:i64,state:State,cancelled:bool,dependencies:Vec<Key> }
struct Dependency { edges:Vec<Key>, owners:BTreeSet<u64> }
#[repr(C)]
#[derive(Clone,Copy,Default)]
pub struct GraphSnapshot { pub resources:u64,pub edges:u64,pub lease_links:u64,pub loading:u64,
    pub ready:u64,pub active:u64,pub retiring:u64,pub registrations:u64,pub physical_releases:u64 }
pub const LAUNCHED:i64=1; pub const READY:i64=2; pub const INSTALLED:i64=3;
pub const RETIRING:i64=4; pub const RELEASED:i64=5; pub const FAILED:i64=6; pub const CANCEL:i64=7;
pub struct Admission { next:u64,leases:BTreeMap<u64,Lease>,denials:u64,forced_sync:u64,
    dependencies:BTreeMap<Key,Dependency>,graph_registrations:u64,physical_releases:u64 }
impl Default for Admission { fn default()->Self { Self{next:1,leases:BTreeMap::new(),denials:0,forced_sync:0,
    dependencies:BTreeMap::new(),graph_registrations:0,physical_releases:0} } }
impl Admission {
    pub fn begin(&mut self,current_epoch:i64,epoch:i64,input:Input)->Result<Decision,i32> {
        if epoch!=current_epoch { return Err(STALE); }
        if input.maximum_workers==0 || input.pinned>1 || input.synchronous>1
            || (input.synchronous!=0 && input.pinned==0) || self.leases.len()>=65536 { return Err(INVALID); }
        let bytes=input.estimated_bytes.checked_add(input.candidate_bytes).ok_or(INVALID)?;
        let reserved=self.leases.values().filter(|lease|lease.state==State::Reserved).count() as u64;
        let workers=input.live_workers.checked_add(reserved).ok_or(INVALID)?;
        let reason=if input.synchronous!=0 { 0 }
            else if input.retiring_roots>0 { 3 }
            else if workers>=input.maximum_workers { 2 }
            else if input.pinned==0 && bytes>input.budget_bytes { 1 }
            else if input.pinned==0 && input.unknown_resources>input.unknown_limit { 4 } else { 0 };
        if reason!=0 { self.denials=self.denials.saturating_add(1).min(i64::MAX as u64); return Ok(Decision{lease:0,reason}); }
        if self.next>i64::MAX as u64 { return Err(INVALID); }
        let id=self.next;self.next+=1;
        self.leases.insert(id,Lease{epoch,state:State::Reserved,cancelled:false,dependencies:Vec::new()});
        if input.synchronous!=0 && (workers>=input.maximum_workers || input.retiring_roots>0
            || bytes>input.budget_bytes || input.unknown_resources>input.unknown_limit) {
            self.forced_sync=self.forced_sync.saturating_add(1).min(i64::MAX as u64);
        }
        Ok(Decision{lease:id,reason:0})
    }
    pub fn event(&mut self,current_epoch:i64,id:u64,epoch:i64,event:i64)->Result<(),i32> {
        let item=self.leases.get_mut(&id).ok_or(INVALID)?;
        if item.epoch!=epoch { return Err(STALE); }
        match event {
            LAUNCHED if item.state==State::Reserved=>item.state=State::Loading,
            READY if item.state==State::Loading=>item.state=State::Ready,
            INSTALLED if item.state==State::Ready && epoch==current_epoch && !item.cancelled=>item.state=State::Active,
            INSTALLED if epoch!=current_epoch || item.cancelled=>return Err(STALE),
            RETIRING if matches!(item.state,State::Ready|State::Active|State::Retiring)=>item.state=State::Retiring,
            CANCEL=>item.cancelled=true,
            RELEASED if matches!(item.state,State::Ready|State::Active|State::Retiring)=>{
                for key in &item.dependencies { if let Some(dependency)=self.dependencies.get_mut(key) {dependency.owners.remove(&id);} }
                self.leases.remove(&id);
            },
            FAILED if matches!(item.state,State::Reserved|State::Loading)=>{
                for key in &item.dependencies { if let Some(dependency)=self.dependencies.get_mut(key) {dependency.owners.remove(&id);} }
                self.leases.remove(&id);
            },
            _=>return Err(INVALID),
        }
        Ok(())
    }
    /// The existing worker has returned. Bind its complete logical source DAG
    /// before READY/install. Existing Resources are the dependency executor;
    /// no additional loader, Godot pointer, byte estimate or retirement clock.
    pub fn bind_dependencies(&mut self,id:u64,epoch:i64,records:&[Descriptor],edges:&[Key])->Result<(),i32> {
        let lease=self.leases.get(&id).ok_or(INVALID)?;
        if lease.epoch!=epoch {return Err(STALE);}
        if !matches!(lease.state,State::Reserved|State::Loading) || !lease.dependencies.is_empty() || records.is_empty()
            || records.len()>MAX_CATALOG || edges.len()>MAX_DEPENDENCIES {return Err(INVALID);}
        let mut candidate:BTreeMap<Key,Vec<Key>>=BTreeMap::new();
        for record in records {
            // Physical CPU/GPU allocation is deliberately unknown in this
            // actual-loader graph. Phase3 estimates remain admission inputs.
            if record.key==[0;4] || record.cpu_bytes!=0 || record.gpu_bytes!=0 || record.flags!=3
                || candidate.contains_key(&record.key) {return Err(INVALID);}
            let start=usize::try_from(record.dependency_start).map_err(|_|INVALID)?;
            let count=usize::try_from(record.dependency_count).map_err(|_|INVALID)?;
            let end=start.checked_add(count).ok_or(INVALID)?;
            let values=edges.get(start..end).ok_or(INVALID)?;
            let sorted:BTreeSet<Key>=values.iter().copied().collect();
            if sorted.len()!=values.len() || sorted.contains(&record.key) {return Err(INVALID);}
            let values:Vec<Key>=sorted.into_iter().collect();
            if let Some(existing)=self.dependencies.get(&record.key) {
                if existing.edges!=values {return Err(INVALID);}
            }
            candidate.insert(record.key,values);
        }
        if self.dependencies.len().checked_add(candidate.keys().filter(|key|!self.dependencies.contains_key(*key)).count()).ok_or(INVALID)?>MAX_CATALOG {
            return Err(INVALID);
        }
        let prior_edges:usize=self.dependencies.iter().filter(|(key,_)|!candidate.contains_key(*key)).map(|(_,value)|value.edges.len()).sum();
        let added_edges:usize=candidate.values().map(Vec::len).sum();
        if prior_edges.checked_add(added_edges).ok_or(INVALID)?>MAX_DEPENDENCIES {return Err(INVALID);}
        // Validate the union before changing any ownership. Incremental source
        // DAG registration cannot introduce missing vertices or a cycle.
        let mut degrees:BTreeMap<Key,usize>=BTreeMap::new();
        let mut reverse:BTreeMap<Key,Vec<Key>>=BTreeMap::new();
        for (key,values) in self.dependencies.iter().map(|(key,value)|(key,&value.edges))
            .filter(|(key,_)|!candidate.contains_key(*key)).chain(candidate.iter()) {
            degrees.insert(*key,values.len());
            for dependency in values {
                if !candidate.contains_key(dependency) && !self.dependencies.contains_key(dependency) {return Err(INVALID);}
                reverse.entry(*dependency).or_default().push(*key);
            }
        }
        let mut ready:Vec<Key>=degrees.iter().filter_map(|(key,count)|(*count==0).then_some(*key)).collect();
        let mut visited=0;
        while let Some(key)=ready.pop() {
            visited+=1;
            for dependent in reverse.get(&key).into_iter().flatten() {
                let count=degrees.get_mut(dependent).ok_or(INVALID)?;*count-=1;
                if *count==0 {ready.push(*dependent);}
            }
        }
        if visited!=degrees.len() {return Err(INVALID);}
        let keys:Vec<Key>=candidate.keys().copied().collect();
        for (key,values) in candidate {
            self.dependencies.entry(key).or_insert_with(||Dependency{edges:values,owners:BTreeSet::new()}).owners.insert(id);
        }
        self.leases.get_mut(&id).ok_or(INVALID)?.dependencies=keys;
        self.graph_registrations=self.graph_registrations.saturating_add(1).min(i64::MAX as u64);
        Ok(())
    }
    /// Owner acknowledges weak actual Resource carriers are gone. A released
    /// root is insufficient while any shared/retained cache Resource survives.
    pub fn release_dependencies(&mut self,keys:&[Key])->Result<Vec<Key>,i32> {
        if keys.len()>MAX_CATALOG {return Err(INVALID);}
        let mut requested:BTreeSet<Key>=keys.iter().copied().collect();
        if requested.len()!=keys.len() || requested.iter().any(|key|!self.dependencies.contains_key(key)) {return Err(INVALID);}
        let mut removed=Vec::new();
        loop {
            let incoming:BTreeSet<Key>=self.dependencies.values().flat_map(|value|value.edges.iter().copied()).collect();
            let available:Vec<Key>=requested.iter().filter(|key|self.dependencies.get(*key).is_some_and(|value|value.owners.is_empty()) && !incoming.contains(*key)).copied().collect();
            if available.is_empty() {break;}
            for key in available {self.dependencies.remove(&key);requested.remove(&key);removed.push(key);}
        }
        self.physical_releases=self.physical_releases.saturating_add(removed.len() as u64).min(i64::MAX as u64);
        Ok(removed)
    }
    pub fn graph_snapshot(&self)->GraphSnapshot {
        let mut result=GraphSnapshot{resources:self.dependencies.len() as u64,registrations:self.graph_registrations,
            physical_releases:self.physical_releases,..GraphSnapshot::default()};
        for dependency in self.dependencies.values() {
            result.edges+=dependency.edges.len() as u64;result.lease_links+=dependency.owners.len() as u64;
            let states:Vec<State>=dependency.owners.iter().filter_map(|id|self.leases.get(id).map(|lease|lease.state)).collect();
            if states.contains(&State::Active) {result.active+=1;}
            else if states.contains(&State::Loading) || states.contains(&State::Reserved) {result.loading+=1;}
            else if states.contains(&State::Ready) {result.ready+=1;} else {result.retiring+=1;}
        }
        result
    }
    pub fn snapshot(&self,epoch:i64)->Snapshot {
        let mut result=Snapshot{denials:self.denials,forced_sync:self.forced_sync,..Snapshot::default()};
        for lease in self.leases.values() {
            match lease.state {State::Reserved=>result.reserved+=1,State::Loading=>result.loading+=1,
                State::Ready=>result.ready+=1,State::Active=>result.active+=1,State::Retiring=>result.retiring+=1}
            result.cancelled+=u64::from(lease.cancelled);result.old_epoch+=u64::from(lease.epoch!=epoch);
        }
        result
    }
}
#[cfg(test)] mod tests {
    use super::*;
    fn input()->Input {Input{budget_bytes:100,maximum_workers:1,unknown_limit:5,..Input::default()}}
    #[test] fn real_reservations_gate_competing_launch_and_cancel_is_not_release() {
        let mut owner=Admission::default();let first=owner.begin(1,1,input()).unwrap().lease;
        assert_eq!(owner.begin(1,1,input()).unwrap().reason,2);
        owner.event(1,first,1,LAUNCHED).unwrap();owner.event(1,first,1,CANCEL).unwrap();
        assert_eq!(owner.snapshot(2).loading,1);assert_eq!(owner.snapshot(2).old_epoch,1);
        owner.event(2,first,1,READY).unwrap();assert_eq!(owner.event(2,first,1,INSTALLED),Err(STALE));
        owner.event(2,first,1,RETIRING).unwrap();assert_eq!(owner.snapshot(2).retiring,1);
        owner.event(2,first,1,RELEASED).unwrap();assert_eq!(owner.snapshot(2).retiring,0);
    }
    #[test] fn mandatory_ground_preserves_sync_overrun_and_unknowns_are_not_zero() {
        let mut owner=Admission::default();let mut dto=input();dto.unknown_resources=6;
        assert_eq!(owner.begin(1,1,dto).unwrap().reason,4);
        dto.pinned=1;dto.live_workers=1;assert_eq!(owner.begin(1,1,dto).unwrap().reason,2);
        dto.synchronous=1;let decision=owner.begin(1,1,dto).unwrap();assert!(decision.lease>0);
        assert_eq!(owner.snapshot(1).forced_sync,1);
    }
    fn descriptor(key:u64,start:u64,count:u64)->Descriptor {
        Descriptor{key:[key;4],flags:3,dependency_start:start,dependency_count:count,..Descriptor::default()}
    }
    #[test] fn actual_lease_dag_shares_transitive_dependencies_until_physical_acknowledgement() {
        let mut owner=Admission::default();let mut dto=input();dto.pinned=1;dto.synchronous=1;
        let a=owner.begin(1,1,dto).unwrap().lease;
        let b=owner.begin(1,1,dto).unwrap().lease;
        for lease in [a,b] {owner.event(1,lease,1,LAUNCHED).unwrap();}
        owner.bind_dependencies(a,1,&[descriptor(1,0,1),descriptor(3,1,1),descriptor(4,2,0)],&[[3;4],[4;4]]).unwrap();
        owner.bind_dependencies(b,1,&[descriptor(2,0,1),descriptor(3,1,1),descriptor(4,2,0)],&[[3;4],[4;4]]).unwrap();
        assert_eq!(owner.graph_snapshot().resources,4);assert_eq!(owner.graph_snapshot().lease_links,6);
        for lease in [a,b] {owner.event(1,lease,1,READY).unwrap();owner.event(1,lease,1,INSTALLED).unwrap();}
        assert_eq!(owner.graph_snapshot().active,4);
        owner.event(1,a,1,RETIRING).unwrap();owner.event(1,a,1,RELEASED).unwrap();
        // Actual root release is not physical Resource release; no automatic
        // graph deletion or fake cache-byte reclamation is performed.
        assert_eq!(owner.graph_snapshot().resources,4);
        assert_eq!(owner.release_dependencies(&[[1;4],[3;4],[4;4]]).unwrap(),vec![[1;4]]);
        assert_eq!(owner.graph_snapshot().resources,3);
        owner.event(2,b,1,CANCEL).unwrap();owner.event(2,b,1,RETIRING).unwrap();owner.event(2,b,1,RELEASED).unwrap();
        assert_eq!(owner.release_dependencies(&[[2;4],[3;4],[4;4]]).unwrap().len(),3);
        assert_eq!(owner.graph_snapshot().resources,0);assert_eq!(owner.graph_snapshot().physical_releases,4);
    }
    #[test] fn dependency_registration_is_atomic_and_does_not_rewrite_existing_identity() {
        let mut owner=Admission::default();let lease=owner.begin(1,1,input()).unwrap().lease;
        owner.event(1,lease,1,LAUNCHED).unwrap();
        assert_eq!(owner.bind_dependencies(lease,1,&[descriptor(1,0,1)],&[[9;4]]),Err(INVALID));
        assert_eq!(owner.graph_snapshot().resources,0);
        assert_eq!(owner.bind_dependencies(lease,1,&[descriptor(1,0,1),descriptor(2,1,1)],&[[2;4],[1;4]]),Err(INVALID));
        assert_eq!(owner.graph_snapshot().resources,0);
        owner.bind_dependencies(lease,1,&[descriptor(1,0,1),descriptor(2,1,0)],&[[2;4]]).unwrap();
        assert_eq!(owner.graph_snapshot().resources,2);
        assert_eq!(owner.release_dependencies(&[[1;4],[2;4]]).unwrap().len(),0);
        owner.event(1,lease,1,READY).unwrap();owner.event(1,lease,1,RELEASED).unwrap();
        assert_eq!(owner.release_dependencies(&[[1;4],[2;4]]).unwrap().len(),2);
    }
}
