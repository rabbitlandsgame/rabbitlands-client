//! Deterministic data-only residency planning. Godot owns every resource, Node,
//! loader job, GPU call, and retirement timer. No pointers or worker threads.
use std::collections::{BTreeMap, BTreeSet, BinaryHeap};
use std::cmp::Reverse;
use crate::{INVALID, STALE};

pub const MAX_CATALOG: usize = 65_536;
pub const MAX_DEPENDENCIES: usize = 262_144;
pub const MAX_ACTIONS: usize = 4_096;
pub type Key = [u64; 4]; // full SHA256 words, never a truncated hash or ObjectID.
pub const UNKNOWN_CPU: u64 = 1;
pub const UNKNOWN_GPU: u64 = 2;
pub const LOAD: i64 = 1;
pub const INSTALL: i64 = 2;
pub const RETIRE: i64 = 3;
pub const CANCEL_LOAD: i64 = 4;
pub const RELEASE_READY: i64 = 5;
pub const LOADED: i64 = 1;
pub const LOAD_FAILED: i64 = 2;
pub const RELEASED: i64 = 3;
pub const INSTALLED: i64 = 4;
pub const INSTALL_FAILED: i64 = 5;

#[repr(C)]
#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
pub struct Descriptor {
    pub key: Key,
    pub cpu_bytes: u64,
    pub gpu_bytes: u64,
    pub flags: u64,
    pub dependency_start: u64,
    pub dependency_count: u64,
}

#[repr(C)]
#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
pub struct Wanted {
    pub key: Key,
    pub priority: i64, // lower first; caller decides terrain/arrival priorities.
    pub pinned: i64,   // 1 = mandatory terrain/visible/arrival/collision safety.
}

#[repr(C)]
#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
pub struct Event {
    pub key: Key,
    pub generation: u64,
    pub epoch: i64,
    pub kind: i64,
}

#[repr(C)]
#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
pub struct Action {
    pub key: Key,
    pub generation: u64,
    pub epoch: i64,
    pub kind: i64,
    pub pinned: i64,
}

#[repr(C)]
#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
pub struct Budget {
    pub cpu_bytes: u64,
    pub gpu_bytes: u64,
    pub in_flight: u64,
    pub unknown_resources: u64,
}

#[repr(C)]
#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
pub struct Snapshot {
    pub epoch: i64,
    pub queued: u64,
    pub loading: u64,
    pub ready: u64,
    pub active: u64,
    pub retiring: u64,
    pub cancel_pending: u64,
    pub cpu_bytes: u64,
    pub gpu_bytes: u64,
    pub unknown_resources: u64,
    pub cpu_over_budget: u64,
    pub gpu_over_budget: u64,
    pub stale_events: u64,
    pub failed: u64,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
enum State { Absent, Loading, Ready, Installing, Active, Retiring }

#[derive(Clone, Debug)]
struct Resource {
    descriptor: Descriptor,
    dependencies: Vec<Key>,
    wanted: Option<(i64, bool)>,
    state: State,
    generation: u64,
    request_epoch: i64,
    cancel_sent: bool,
    failed: bool,
}

#[derive(Clone, Debug)]
pub struct Planner {
    epoch: i64,
    next_generation: u64,
    resources: BTreeMap<Key, Resource>,
    dependents: BTreeMap<Key, Vec<Key>>,
    workset: BTreeSet<Key>,
    stale_events: u64,
}

impl Default for Planner {
    fn default() -> Self {
        Self { epoch: 1, next_generation: 1, resources: BTreeMap::new(),
            dependents:BTreeMap::new(),workset:BTreeSet::new(),stale_events:0 }
    }
}

impl Planner {
    pub fn reset(&mut self, epoch: i64) -> Result<(), i32> {
        if epoch <= self.epoch { return Err(STALE); }
        self.epoch = epoch;
        // Never erase allocated/loading records at a session reset. Their old
        // epoch remains valid ONLY for resource release/completion accounting;
        // they cannot install into the new session. Generations never reuse.
        for item in self.resources.values_mut() { item.wanted=None; item.failed=false; }
        self.workset.retain(|key| self.resources[key].state!=State::Absent);
        Ok(())
    }

    pub fn set_catalog(&mut self, descriptors: &[Descriptor], dependencies: &[Key]) -> Result<(), i32> {
        if descriptors.len() > MAX_CATALOG || dependencies.len() > MAX_DEPENDENCIES {
            return Err(INVALID);
        }
        if self.resources.values().any(|item| item.state != State::Absent || item.wanted.is_some()) {
            return Err(STALE);
        }
        let mut candidate = BTreeMap::new();
        let (mut total_cpu,mut total_gpu)=(0u64,0u64);
        for descriptor in descriptors {
            total_cpu=total_cpu.checked_add(descriptor.cpu_bytes).ok_or(INVALID)?;
            total_gpu=total_gpu.checked_add(descriptor.gpu_bytes).ok_or(INVALID)?;
            let begin = usize::try_from(descriptor.dependency_start).map_err(|_| INVALID)?;
            let count = usize::try_from(descriptor.dependency_count).map_err(|_| INVALID)?;
            let end = begin.checked_add(count).ok_or(INVALID)?;
            if descriptor.key == [0;4] || descriptor.flags & !(UNKNOWN_CPU | UNKNOWN_GPU) != 0
                || end > dependencies.len() || candidate.contains_key(&descriptor.key)
                || total_cpu>i64::MAX as u64 || total_gpu>i64::MAX as u64 {
                return Err(INVALID);
            }
            let mut deps = dependencies[begin..end].to_vec();
            deps.sort_unstable();
            if deps.windows(2).any(|pair| pair[0] == pair[1]) || deps.contains(&descriptor.key) {
                return Err(INVALID);
            }
            candidate.insert(descriptor.key, Resource { descriptor: *descriptor, dependencies: deps,
                wanted: None, state: State::Absent, generation: 0, request_epoch: self.epoch, cancel_sent: false, failed: false });
        }
        if candidate.values().flat_map(|item| &item.dependencies).any(|key| !candidate.contains_key(key)) {
            return Err(INVALID);
        }
        // Iterative Kahn validation avoids recursive-stack overflow on a large
        // catalog and establishes a strict dependency DAG before publication.
        let mut degrees: BTreeMap<Key, usize> = candidate.iter().map(|(key,item)| (*key,item.dependencies.len())).collect();
        let mut reverse: BTreeMap<Key, Vec<Key>> = BTreeMap::new();
        for (key,item) in &candidate {
            for dep in &item.dependencies { reverse.entry(*dep).or_default().push(*key); }
        }
        let mut leaves: Vec<Key> = degrees.iter().filter_map(|(key,n)| (*n == 0).then_some(*key)).collect();
        let mut visited = 0;
        while let Some(key) = leaves.pop() {
            visited += 1;
            for parent in reverse.get(&key).into_iter().flatten() {
                let n = degrees.get_mut(parent).ok_or(INVALID)?;
                *n -= 1;
                if *n == 0 { leaves.push(*parent); }
            }
        }
        if visited != candidate.len() { return Err(INVALID); }
        self.resources = candidate;
        self.dependents=reverse;
        self.workset.clear();
        Ok(())
    }

    pub fn reconcile(&mut self, epoch: i64, roots: &[Wanted]) -> Result<(), i32> {
        if epoch != self.epoch { return Err(STALE); }
        if roots.len() > MAX_CATALOG { return Err(INVALID); }
        let mut desired: BTreeMap<Key,(i64,bool)> = BTreeMap::new();
        let mut work = BinaryHeap::new();
        let mut roots_seen = BTreeSet::new();
        for wanted in roots {
            if !(0..=1).contains(&wanted.pinned) || !self.resources.contains_key(&wanted.key)
                || !roots_seen.insert(wanted.key) { return Err(INVALID); }
            work.push(Reverse((wanted.priority,wanted.pinned==0,wanted.key)));
        }
        while let Some(Reverse((priority,not_pinned,key))) = work.pop() {
            let pinned=!not_pinned;
            if let Some((old_priority,old_pin)) = desired.get(&key) {
                if *old_priority <= priority && (*old_pin || !pinned) { continue; }
            }
            let old = desired.get(&key).copied().unwrap_or((priority,false));
            let merged = (priority.min(old.0), pinned || old.1);
            desired.insert(key,merged);
            for dep in &self.resources[&key].dependencies { work.push(Reverse((merged.0,!merged.1,*dep))); }
        }
        // Only publish after all roots and their closure have validated.
        for key in &self.workset { self.resources.get_mut(key).ok_or(INVALID)?.wanted=None; }
        for (key,wanted) in desired { self.resources.get_mut(&key).ok_or(INVALID)?.wanted=Some(wanted); self.workset.insert(key); }
        self.workset.retain(|key| self.resources[key].state!=State::Absent || self.resources[key].wanted.is_some());
        Ok(())
    }

    pub fn retry_failed(&mut self, epoch:i64, keys:&[Key]) -> Result<(),i32> {
        if epoch != self.epoch { return Err(STALE); }
        if keys.len()>MAX_CATALOG || keys.iter().any(|key| !self.resources.contains_key(key)
            || self.resources[key].state != State::Absent) { return Err(INVALID); }
        for key in keys { self.resources.get_mut(key).ok_or(INVALID)?.failed=false; }
        Ok(())
    }

    fn transition(item:&mut Resource,event:Event) -> Result<(),i32> {
        if event.generation != item.generation || event.epoch != item.request_epoch {
            return Err(STALE);
        }
        // Stale-but-owned completions move toward release, never install.
        // A cancellation request cannot claim that an engine load disappeared.
        match (item.state, event.kind) {
            (State::Loading, LOADED) => item.state = State::Ready,
            (State::Loading, LOAD_FAILED) => { item.state = State::Absent; item.failed=true; },
            (State::Installing, INSTALLED) => item.state = State::Active,
            (State::Installing, INSTALL_FAILED) => { item.state = State::Ready; item.failed=true; },
            (State::Retiring, RELEASED) => item.state = State::Absent,
            _ => return Err(INVALID),
        }
        if item.state == State::Absent { item.cancel_sent = false; }
        Ok(())
    }

    pub fn event(&mut self,event:Event)->Result<(),i32> { self.events(&[event]) }

    pub fn events(&mut self,events:&[Event])->Result<(),i32> {
        if events.len()>MAX_CATALOG { return Err(INVALID); }
        // Only clone touched records, never the immutable catalog or the full
        // resident graph per frame. Validate the complete event batch first.
        let mut updates:BTreeMap<Key,Resource>=BTreeMap::new();
        for event in events {
            if !updates.contains_key(&event.key) {
                let item=self.resources.get(&event.key).ok_or(INVALID)?.clone();
                updates.insert(event.key,item);
            }
            if let Err(error)=Self::transition(updates.get_mut(&event.key).ok_or(INVALID)?,*event) {
                if error==STALE { self.stale_events=self.stale_events.saturating_add(1).min(i64::MAX as u64); }
                return Err(error);
            }
        }
        for (key,item) in updates {
            if item.state==State::Absent && item.wanted.is_none() { self.workset.remove(&key); }
            self.resources.insert(key,item);
        }
        Ok(())
    }

    fn live_dependent(&self, dependency: Key) -> bool {
        self.dependents.get(&dependency).into_iter().flatten()
            .any(|key| self.resources[key].state!=State::Absent)
    }

    pub fn step(&mut self, epoch: i64, budget: Budget, capacity: usize) -> Result<Vec<Action>, i32> {
        if epoch != self.epoch { return Err(STALE); }
        if capacity > MAX_ACTIONS || budget.in_flight == 0 { return Err(INVALID); }
        // Plan into bounded output first. All validation/overflow failures
        // precede publication; no full-catalog clone or lost reservations.
        let mut actions = Vec::with_capacity(capacity);
        let mut keys: Vec<Key> = self.workset.iter().copied().collect();
        keys.sort_by_key(|key| {
            let item = &self.resources[key];
            let (priority,pinned) = item.wanted.unwrap_or((i64::MAX,false));
            (!pinned,priority,*key)
        });
        for key in &keys {
            if actions.len() == capacity { break; }
            let item = &self.resources[key];
            let obsolete = item.request_epoch != epoch || item.wanted.is_none() || item.cancel_sent || item.failed;
            let kind = if obsolete && item.state == State::Loading && !item.cancel_sent { CANCEL_LOAD }
                else if obsolete && matches!(item.state,State::Ready|State::Active)
                    && !self.live_dependent(*key) {
                    if item.state == State::Ready { RELEASE_READY } else { RETIRE }
                } else { continue; };
            actions.push(Action { key:*key,generation:item.generation,epoch:item.request_epoch,kind,pinned:0 });
        }
        for key in &keys {
            if actions.len() == capacity { break; }
            let item = &self.resources[key];
            let Some((_,pinned)) = item.wanted else { continue; };
            if item.request_epoch != epoch || item.cancel_sent || item.failed || item.state != State::Ready { continue; }
            if !item.dependencies.iter().all(|dep| self.resources[dep].state == State::Active
                && self.resources[dep].request_epoch == epoch) { continue; }
            actions.push(Action { key:*key,generation:item.generation,epoch,kind:INSTALL,pinned:i64::from(pinned) });
        }
        let mut current=self.snapshot(budget);
        let mut next_generation=self.next_generation;
        for key in &keys {
            if actions.len() == capacity { break; }
            let item = &self.resources[key];
            let Some((_,pinned)) = item.wanted else { continue; };
            if item.state != State::Absent || item.failed { continue; }
            if !item.dependencies.iter().all(|dep| self.resources[dep].state == State::Active
                && self.resources[dep].request_epoch == epoch) { continue; }
            if current.loading >= budget.in_flight { break; }
            let cpu = current.cpu_bytes.checked_add(item.descriptor.cpu_bytes).ok_or(INVALID)?;
            let gpu = current.gpu_bytes.checked_add(item.descriptor.gpu_bytes).ok_or(INVALID)?;
            let unknown = current.unknown_resources + u64::from(item.descriptor.flags != 0);
            // Mandatory collision/arrival roots remain visible and can exceed
            // estimates. This overrun is explicit, never disguised as free.
            if !pinned && (cpu > budget.cpu_bytes || gpu > budget.gpu_bytes
                || unknown > budget.unknown_resources) { continue; }
            if next_generation > i64::MAX as u64 { return Err(INVALID); }
            let generation=next_generation;
            next_generation+=1;
            current.loading+=1; current.cpu_bytes=cpu; current.gpu_bytes=gpu; current.unknown_resources=unknown;
            actions.push(Action { key:*key,generation,epoch,kind:LOAD,pinned:i64::from(pinned) });
        }
        for action in &actions {
            let item=self.resources.get_mut(&action.key).ok_or(INVALID)?;
            match action.kind {
                LOAD=>{ item.state=State::Loading; item.generation=action.generation;
                    item.request_epoch=epoch; item.cancel_sent=false; },
                INSTALL=>item.state=State::Installing,
                CANCEL_LOAD=>item.cancel_sent=true,
                RETIRE|RELEASE_READY=>item.state=State::Retiring,
                _=>unreachable!(),
            }
        }
        self.next_generation=next_generation;
        Ok(actions)
    }

    pub fn snapshot(&self, budget: Budget) -> Snapshot {
        let mut result = Snapshot { epoch:self.epoch,stale_events:self.stale_events,..Snapshot::default() };
        for key in &self.workset {
            let item=&self.resources[key];
            result.failed += u64::from(item.failed);
            match item.state {
                State::Absent => { if item.wanted.is_some() && !item.failed { result.queued += 1; } continue; },
                State::Loading => result.loading += 1,
                State::Ready | State::Installing => result.ready += 1,
                State::Active => result.active += 1,
                State::Retiring => result.retiring += 1,
            }
            result.cancel_pending += u64::from(item.cancel_sent);
            result.cpu_bytes = result.cpu_bytes.saturating_add(item.descriptor.cpu_bytes);
            result.gpu_bytes = result.gpu_bytes.saturating_add(item.descriptor.gpu_bytes);
            result.unknown_resources += u64::from(item.descriptor.flags != 0);
        }
        result.cpu_over_budget = result.cpu_bytes.saturating_sub(budget.cpu_bytes);
        result.gpu_over_budget = result.gpu_bytes.saturating_sub(budget.gpu_bytes);
        result
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    fn key(value:u64)->Key { [value,0,0,0] }
    fn descriptor(id:u64,start:u64,count:u64)->Descriptor {
        Descriptor {key:key(id),cpu_bytes:4,gpu_bytes:8,dependency_start:start,dependency_count:count,..Descriptor::default()}
    }
    fn budget()->Budget { Budget {cpu_bytes:100,gpu_bytes:100,in_flight:2,unknown_resources:0} }
    fn ack(planner:&mut Planner,action:Action,kind:i64) {
        planner.event(Event{key:action.key,generation:action.generation,epoch:action.epoch,kind}).unwrap();
    }
    fn want(planner:&mut Planner,id:u64,pinned:i64) {
        planner.reconcile(planner.epoch,&[Wanted{key:key(id),priority:0,pinned}]).unwrap();
    }
    fn activate(planner:&mut Planner)->Action {
        let load=planner.step(planner.epoch,budget(),1).unwrap()[0]; assert_eq!(load.kind,LOAD);
        ack(planner,load,LOADED);
        let install=planner.step(planner.epoch,budget(),1).unwrap()[0]; assert_eq!(install.kind,INSTALL);
        ack(planner,install,INSTALLED); install
    }
    #[test]
    fn dependencies_load_install_and_release_in_ownership_order() {
        let mut planner=Planner::default();
        planner.set_catalog(&[descriptor(1,0,1),descriptor(2,1,0)],&[key(2)]).unwrap();
        want(&mut planner,1,1);
        assert_eq!(activate(&mut planner).key,key(2));
        assert_eq!(activate(&mut planner).key,key(1));
        assert_eq!(planner.snapshot(budget()).gpu_bytes,16);
        planner.reconcile(1,&[]).unwrap();
        let first=planner.step(1,budget(),8).unwrap();
        assert_eq!(first.len(),1); assert_eq!(first[0].key,key(1));
        assert_eq!(planner.snapshot(budget()).gpu_bytes,16); // retiring still owned.
        ack(&mut planner,first[0],RELEASED);
        let second=planner.step(1,budget(),8).unwrap();
        assert_eq!(second[0].key,key(2)); ack(&mut planner,second[0],RELEASED);
        assert_eq!(planner.snapshot(budget()).gpu_bytes,0);
    }
    #[test]
    fn reset_keeps_inflight_until_real_completion_and_release() {
        let mut planner=Planner::default(); planner.set_catalog(&[descriptor(1,0,0)],&[]).unwrap();
        want(&mut planner,1,1); let load=planner.step(1,budget(),1).unwrap()[0];
        planner.reset(2).unwrap(); want(&mut planner,1,1);
        let cancel=planner.step(2,budget(),1).unwrap()[0]; assert_eq!(cancel.kind,CANCEL_LOAD);
        assert_eq!(planner.snapshot(budget()).loading,1);
        assert!(planner.step(2,budget(),1).unwrap().is_empty());
        ack(&mut planner,load,LOADED);
        let release=planner.step(2,budget(),1).unwrap()[0]; assert_eq!(release.kind,RELEASE_READY);
        ack(&mut planner,release,RELEASED);
        let next=planner.step(2,budget(),1).unwrap()[0];
        assert_eq!(next.epoch,2); assert!(next.generation>load.generation);
        assert_eq!(planner.event(Event{key:load.key,generation:load.generation,epoch:1,kind:LOADED}),Err(STALE));
    }
    #[test]
    fn capacity_zero_does_not_reserve_or_drop_work() {
        let mut planner=Planner::default(); planner.set_catalog(&[descriptor(1,0,0)],&[]).unwrap();
        want(&mut planner,1,0); assert!(planner.step(1,budget(),0).unwrap().is_empty());
        assert_eq!(planner.snapshot(budget()).queued,1);
        assert_eq!(planner.step(1,budget(),1).unwrap()[0].generation,1);
    }
    #[test]
    fn mandatory_unknown_cost_is_explicit_while_optional_is_bounded() {
        let mut planner=Planner::default(); let mut row=descriptor(1,0,0); row.flags=UNKNOWN_GPU;
        planner.set_catalog(&[row],&[]).unwrap(); want(&mut planner,1,0);
        assert!(planner.step(1,budget(),1).unwrap().is_empty());
        want(&mut planner,1,1); let mut tiny=budget(); tiny.gpu_bytes=1;
        assert_eq!(planner.step(1,tiny,1).unwrap()[0].pinned,1);
        let stats=planner.snapshot(tiny); assert_eq!(stats.unknown_resources,1); assert_eq!(stats.gpu_over_budget,7);
    }
    #[test]
    fn bad_catalog_and_reconcile_preserve_existing_state() {
        let mut planner=Planner::default(); planner.set_catalog(&[descriptor(1,0,0)],&[]).unwrap();
        assert_eq!(planner.set_catalog(&[descriptor(2,0,1),descriptor(3,1,1)],&[key(3),key(2)]),Err(INVALID));
        assert_eq!(planner.set_catalog(&[descriptor(2,0,1)],&[key(9)]),Err(INVALID));
        want(&mut planner,1,0);
        assert_eq!(planner.reconcile(1,&[Wanted{key:key(9),priority:0,pinned:0}]),Err(INVALID));
        assert_eq!(planner.snapshot(budget()).queued,1);
    }
    #[test]
    fn same_epoch_cancel_does_not_install_if_desired_returns() {
        let mut planner=Planner::default(); planner.set_catalog(&[descriptor(1,0,0)],&[]).unwrap();
        want(&mut planner,1,0); let load=planner.step(1,budget(),1).unwrap()[0];
        planner.reconcile(1,&[]).unwrap(); let cancel=planner.step(1,budget(),1).unwrap()[0];
        assert_eq!(cancel.kind,CANCEL_LOAD); want(&mut planner,1,0); ack(&mut planner,load,LOADED);
        // Cancelled completions cannot be installed/reused, even when interest
        // returns. Release first, then use a distinct generation.
        let action=planner.step(1,budget(),1).unwrap();
        assert_eq!(action.len(),1); assert_eq!(action[0].kind,RELEASE_READY);
    }
    #[test]
    fn failed_load_does_not_retry_each_frame_or_erase_interest() {
        let mut planner=Planner::default(); planner.set_catalog(&[descriptor(1,0,0)],&[]).unwrap();
        want(&mut planner,1,0); let load=planner.step(1,budget(),1).unwrap()[0];
        ack(&mut planner,load,LOAD_FAILED);
        for _ in 0..8 { assert!(planner.step(1,budget(),1).unwrap().is_empty()); }
        assert_eq!(planner.snapshot(budget()).failed,1);
        planner.retry_failed(1,&[key(1)]).unwrap();
        assert!(planner.step(1,budget(),1).unwrap()[0].generation>load.generation);
    }
}
