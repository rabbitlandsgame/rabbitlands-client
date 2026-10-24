//! Optional remote presentation. No Godot objects, authoritative actor data, or clip clocks.
//! Wire v1: fixed 47-double state, followed by four f32 pace arrays and one
//! unconfirmed array, each prefixed by its length. f32 round trips are intentional.
use std::collections::HashMap;
use std::panic::{catch_unwind, AssertUnwindSafe};
use std::slice;

const INVALID: i32 = 1;
const STALE: i32 = 2;
const INTERNAL: i32 = 3;
pub const FIXED: usize = 47;
const LIMIT: usize = 65536;
const SNAP: i64 = 1;
const TRAVEL: i64 = 2;
const SETTLED: i64 = 4;
const COMBAT: i64 = 8;
const AIM: i64 = 16;
const HASTE: i64 = 32;
const MOUNT: i64 = 64;
const CREATURE: i64 = 128;
const FACING: i64 = 256;
const SLEEP: i64 = 512; // dead physics stopped; separate from legacy _settled
const PI: f64 = std::f64::consts::PI;

#[derive(Clone)]
pub struct State { v: [f64; FIXED], histories: [Vec<f32>; 4], unconfirmed: Vec<f32> }
impl State {
    fn parse(p: &[f64]) -> Result<Self,i32> {
        if p.len() < FIXED+5 || !p.iter().all(|v|v.is_finite()) { return Err(INVALID); }
        let mut v=[0.;FIXED]; v.copy_from_slice(&p[..FIXED]);
        for k in [14,19,26,27,28,29,46] {
            if v[k].fract()!=0. || v[k].abs()>9_007_199_254_740_991. {return Err(INVALID);}
        }
        if !(0..=3).contains(&(v[19] as i64)) || !(-1..=3).contains(&(v[46] as i64))
            || !(0..=22).contains(&(v[26] as i64)) || !(0..=1023).contains(&(v[29] as i64))
            || v[12]<0. || v[13]<0. || v[15]<=0. || v[18]<=0. || v[31]<=0.
            || v[34]<=0. || v[35]<=0. || v[36]<0. || v[38]<0. || v[40]<0.
            || v[41]<v[40] || v[42]<0. || v[43]<0. {return Err(INVALID);}
        let mut histories: [Vec<f32>;4]=std::array::from_fn(|_|Vec::new());
        let mut at=FIXED;
        for h in &mut histories { *h=read_history(p,&mut at,12)?; }
        // Never truncate an unconfirmed history during transfer. The cap rejects
        // unsupported pathological state before ownership is changed.
        let unconfirmed=read_history(p,&mut at,LIMIT)?;
        if at!=p.len(){return Err(INVALID);}
        Ok(Self{v,histories,unconfirmed})
    }
    fn write(&self,out:&mut Vec<f64>,full:bool) {
        out.extend_from_slice(&self.v);
        if full {for h in self.histories.iter().chain(std::iter::once(&self.unconfirmed)) {
            out.push(h.len() as f64);out.extend(h.iter().map(|x|f64::from(*x)));
        }}
    }
    fn flags(&self)->i64 {self.v[29] as i64}
    fn has(&self,f:i64)->bool {self.flags()&f!=0}
    fn set(&mut self,f:i64,on:bool){self.v[29]=if on{self.flags()|f}else{self.flags()&!f} as f64;}
    fn quantize_transform(&mut self){for k in [0,1,2,9]{self.v[k]=f64::from(self.v[k] as f32);}}
    fn pace(&self,g:usize)->f64 {
        if self.has(MOUNT){return self.v[30];}
        if !self.histories[g].is_empty(){return median(&self.histories[g],self.v[34]);}
        if !self.histories[g^2].is_empty(){return median(&self.histories[g^2],self.v[34])*if g&2!=0{0.5}else{2.};}
        self.v[if g&1!=0{35}else{34}]*if g&2!=0{0.5}else{1.}
    }
    fn paced(&self,action:i64)->i64 {
        if action!=2{return action;}
        if self.has(HASTE){return 3;}
        let speed=if self.v[13]>0.{distance(&self.v,6,3)/self.v[13]}else{self.v[20]};
        if self.has(CREATURE)&&self.v[44]>0.&&self.v[45]>self.v[44]&&speed>self.v[44]*1.8{3}else{action}
    }
    fn aware(&self,action:i64,changed:bool)->i64 {
        if self.v[13]>0.&&[0,1,4].contains(&action){return self.paced(if self.v[19] as i64&1!=0{3}else{2});}
        if ![2,3].contains(&action){return action;}
        if changed||self.v[13]>0.||self.v[21]>0.{action}else{0}
    }
    // Input: target xyz, authoritative yaw, arrival msec, step msec, playout,
    // command, sequence, inCombat, haste, stamped, teleport, facingCommand,
    // mountPace, mounted, walkStride, runStride, then the 13 pacing parameters.
    // Visual metadata is supplied at
    // the touched boundary, not exported from every actor on every frame.
    fn movement(&mut self,p:&[f64])->(bool,bool,bool) {
        self.v[31..44].copy_from_slice(&p[18..31]);
        let previous=[self.v[3],self.v[4],self.v[5]];
        let changed=dist3(previous,[p[0],p[1],p[2]])>0.001;
        let combat_changed=(p[9]!=0.)!=self.has(COMBAT);
        let fresh=p[8]!=self.v[27];self.v[27]=p[8];self.set(COMBAT,p[9]!=0.);
        if combat_changed||(fresh&&[18.,19.].contains(&p[7])) {
            self.v[14]=-1.;self.unconfirmed.clear();self.v[46]=-1.;self.v[16]=0.;self.v[17]=-1.;
        }
        self.v[3..6].copy_from_slice(&p[0..3]);self.v[10]=p[3];self.set(HASTE,p[10]!=0.);
        self.v[30]=p[14];self.set(MOUNT,p[15]!=0.);self.v[44]=p[16];self.v[45]=p[17];
        self.v[20]=if self.has(HASTE)||(30.0..=37.0).contains(&p[7]){self.v[33]}else{self.v[32]};
        let gait=(if (30.0..=37.0).contains(&p[13]){1}else{0})|if self.has(HASTE){2}else{0};
        if p[12]!=0.||distance(&self.v,0,3)>if self.has(CREATURE){64.}else{8.} {
            for k in 0..3{self.v[k]=self.v[3+k];self.v[6+k]=self.v[3+k];}
            self.v[9]=self.v[10];self.v[12]=0.;self.v[13]=0.;self.v[14]=-1.;
            for h in &mut self.histories{h.clear();}self.v[15]=self.pace(gait);
            self.unconfirmed.clear();self.v[46]=-1.;self.v[16]=0.;self.v[17]=-1.;self.v[18]=1.;
            self.v[19]=gait as f64;self.v[21]=0.;self.set(SNAP,false);self.set(TRAVEL,false);
        }else if changed {
            let now=if p[11]!=0.{p[5]}else{p[4]};
            let tiles=(dist3(previous,[p[0],p[1],p[2]])/self.v[31]).max(0.001);
            if self.v[14]>=0. {
                let observed=(now-self.v[14])/1000.;let gap_tiles=self.v[18].max(0.001);
                let gap=(observed/gap_tiles).max(0.05);let old=self.v[19] as usize;
                let idle=gap>self.v[41];
                let standing=idle||(self.histories[old].len()>=3&&pause(observed,median(&self.histories[old],self.v[15])*gap_tiles));
                if idle{self.unconfirmed.clear();}
                else if standing {
                    if self.v[46]!=old as f64{self.unconfirmed.clear();self.v[46]=old as f64;}
                    self.unconfirmed.push(gap as f32);
                    if self.unconfirmed.len()>=5 {
                        let recent=&self.unconfirmed[self.unconfirmed.len()-5..];
                        let low=recent.iter().copied().fold(f32::INFINITY,f32::min);
                        let high=recent.iter().copied().fold(f32::NEG_INFINITY,f32::max);
                        if f64::from(high)<=f64::from(low)*1.15{self.histories[old]=recent.to_vec();self.unconfirmed.clear();}
                    }
                }else {
                    self.unconfirmed.clear();self.histories[old].push(gap as f32);
                    if self.histories[old].len()>12{self.histories[old].remove(0);}
                }
                self.v[15]=self.pace(old);let expected=self.v[15]*gap_tiles;
                let late=if standing||pause(observed,expected){0.}else{observed-expected};
                self.v[16]=late.max(self.v[16]*0.98).clamp(0.,self.v[38]);
            }
            self.v[15]=self.pace(gait);
            self.v[20]=self.v[20].max(self.v[31]/self.v[15].max(0.001)*self.v[39].max(1.));
            self.v[14]=now;self.v[18]=tiles;self.v[19]=gait as f64;
            for k in 0..3{self.v[6+k]=self.v[k];}self.v[12]=0.;self.v[21]=0.;
            let cadence=self.v[15]*tiles;
            let earliest=now/1000.+if p[11]!=0.{cadence+p[6]}else{cadence*self.v[37]+self.v[16]};
            let continued=self.v[17]+cadence;
            let due=if continued<=earliest{earliest}else{earliest.max(self.v[17]+cadence/if p[11]!=0.{1.03}else{self.v[39].max(1.)})};
            let floor=if self.has(MOUNT){self.v[40].min(cadence)}else{self.v[40]};
            self.v[13]=(due-p[4]/1000.).max(distance(&self.v,0,3)/self.v[20].max(0.001)).clamp(floor,self.v[41]+self.v[38]);
            self.v[17]=p[4]/1000.+self.v[13];
            let dx=f64::from(self.v[3] as f32-self.v[6] as f32);let dz=f64::from(self.v[5] as f32-self.v[8] as f32);
            self.v[11]=if dx*dx+dz*dz<0.000001{self.v[10]}else{(-dx).atan2(-dz)};
            self.set(TRAVEL,true);
        }
        self.set(SETTLED,false);self.set(SLEEP,false);self.quantize_transform();(changed,combat_changed,fresh)
    }
    fn tick(&mut self,dt:f64)->i64 {
        if self.v[26]==5. {for k in 0..3{self.v[k]=self.v[3+k];}self.v[9]=position_write_yaw(self.v[9]);self.set(SLEEP,true);self.quantize_transform();return -1;}
        if self.has(SNAP){
            for k in 0..3{self.v[k]=self.v[3+k];self.v[6+k]=self.v[3+k];}
            self.v[9]=f64::from(self.v[10] as f32);self.set(SNAP,false);self.set(TRAVEL,false);self.settle();self.quantize_transform();return -1;
        }
        if self.v[13]>0. {
            self.v[12]=(self.v[12]+dt).min(self.v[13]);let t=self.v[12]/self.v[13];
            for k in 0..3{let from=self.v[6+k] as f32;self.v[k]=f64::from(from+(self.v[3+k] as f32-from)*t as f32);}
            if t>=1. {
                for k in 0..3{self.v[k]=self.v[3+k];}self.v[13]=0.;self.set(TRAVEL,false);
                if [2.,3.].contains(&self.v[26]){self.v[21]=self.v[42].max(self.v[15]*0.75);}
            }
        }else {for k in 0..3{self.v[k]=self.v[3+k];}self.set(TRAVEL,false);}
        let desired=if self.has(TRAVEL){self.v[11]}else{self.v[10]};
        // Legacy writes global_position before reading rotation.y. Node3D
        // rebuilds its float Basis, marks Euler dirty and reads the canonical
        // yaw back before rotate_toward. A rotation setter may then hold an
        // unwrapped result until the NEXT position write; do not wrap output.
        self.v[9]=f64::from(rotate(position_write_yaw(self.v[9]),desired,self.v[36]*dt) as f32);
        if !self.has(MOUNT)&&self.has(FACING)&&!approx(self.v[22],self.v[24]) {
            self.v[25]+=dt;let t=if self.v[43]<=0.{1.}else{(self.v[25]/self.v[43]).clamp(0.,1.)};
            self.v[22]=self.v[23]+angle_delta(self.v[24]-self.v[23])*t;
            if t>=1.{self.v[22]=self.v[24];}
        }
        let mut action=-1;
        if self.v[21]>0.{self.v[21]=(self.v[21]-dt).max(0.);if self.v[21]<=0.&&[2.,3.].contains(&self.v[26]){action=0;}}
        self.settle();self.quantize_transform();action
    }
    fn settle(&mut self) {
        if self.has(SNAP)||self.v[13]>0.||self.v[21]>0.||angle(self.v[10]-self.v[9]).abs()>0.0005||!approx(self.v[22],self.v[24]){return;}
        for k in 0..3{self.v[k]=self.v[3+k];}self.v[9]=self.v[10];self.set(SETTLED,true);
    }
}
fn read_history(p:&[f64],at:&mut usize,limit:usize)->Result<Vec<f32>,i32>{
    if *at>=p.len()||p[*at].fract()!=0.||p[*at]<0.||p[*at]>limit as f64{return Err(INVALID);}
    let n=p[*at] as usize;*at+=1;if n>p.len()-*at{return Err(INVALID);}
    let mut h=Vec::with_capacity(n);for v in &p[*at..*at+n]{if *v<=0.||*v>f64::from(f32::MAX){return Err(INVALID);}h.push(*v as f32);}*at+=n;Ok(h)
}
fn median(h:&[f32],fallback:f64)->f64{if h.is_empty(){return fallback;}let mut h=h.to_vec();h.sort_by(f32::total_cmp);let m=h.len()/2;if h.len()%2==1{f64::from(h[m])}else{(f64::from(h[m-1])+f64::from(h[m]))*0.5}}
fn pause(observed:f64,expected:f64)->bool{observed-expected>expected.min(0.4)}
fn dist3(a:[f64;3],b:[f64;3])->f64{let d=[a[0] as f32-b[0] as f32,a[1] as f32-b[1] as f32,a[2] as f32-b[2] as f32];f64::from((d[0]*d[0]+d[1]*d[1]+d[2]*d[2]).sqrt())}
fn distance(v:&[f64],a:usize,b:usize)->f64{dist3([v[a],v[a+1],v[a+2]],[v[b],v[b+1],v[b+2]])}
fn angle(a:f64)->f64{(a+PI).rem_euclid(2.*PI)-PI}
// Godot's signed antipodal tie differs from a [-PI,PI) wrap. Keep the
// angle_difference/lerp_angle convention for rotations and facing blends.
fn angle_delta(a:f64)->f64{let d=a%(2.*PI);(2.*d)%(2.*PI)-d}
// Supported actors rotate around local Y. The single-precision engine's
// Basis::get_euler(YXZ) reads atan2(m02,m22) after a position-write round trip.
fn position_write_yaw(yaw:f64)->f64{let yaw=yaw as f32;f64::from(yaw.sin().atan2(yaw.cos()))}
fn rotate(from:f64,to:f64,step:f64)->f64{let d=angle_delta(to-from);from+(if d>=0.{1.}else{-1.})*step.min(d.abs())}
fn approx(a:f64,b:f64)->bool{a==b||(a-b).abs()<(0.00001*a.abs()).max(0.00001)}

struct Row{id:i64,generation:i64,state:State,alive:bool}
#[derive(Default)]
pub struct Remote {
    epoch:i64,map:i64,sequence:i64,last_tick:i64,rows:Vec<Row>,lookup:HashMap<i64,usize>,generations:HashMap<i64,i64>,
    meta:Vec<i64>,values:Vec<f64>,gate:Gate,
}
impl Remote {
    fn event(&mut self,op:i64,id:i64,generation:i64,epoch:i64,sequence:i64,map:i64,p:&[f64])->Result<(),i32>{
        if epoch!=self.epoch||map!=self.map||sequence<=self.sequence{return Err(STALE);}
        if id<0||generation<=0||!p.iter().all(|v|v.is_finite()){return Err(INVALID);}
        if op==1 {
            if self.lookup.contains_key(&id)||self.lookup.len()>=LIMIT||self.generations.get(&id).is_some_and(|g|generation<=*g){return Err(STALE);}
            if !self.generations.contains_key(&id)&&self.generations.len()>=LIMIT{return Err(INVALID);}
            let state=State::parse(p)?;let slot=self.rows.len();self.rows.push(Row{id,generation,state,alive:true});
            self.lookup.insert(id,slot);self.generations.insert(id,generation);
        }else {
            let slot=*self.lookup.get(&id).ok_or(STALE)?;
            if self.rows[slot].generation!=generation{return Err(STALE);}
            match op {
                2=>{
                    if p.len()!=31||p[14]<=0.||p[18]<=0.||p[21]<=0.||p[22]<=0.||p[23]<0.
                        ||p[25]<0.||p[27]<0.||p[28]<p[27]||p[29]<0.||p[30]<0.
                        ||[7,8,9,10,11,12,13,15].iter().any(|i|p[*i].fract()!=0.){return Err(INVALID);}
                    if self.rows[slot].state.unconfirmed.len()>=LIMIT{return Err(INVALID);}
                    let flags=self.rows[slot].state.movement(p);
                    self.meta.clear();self.meta.extend([id,generation,epoch,map,sequence,flags.0 as i64,flags.1 as i64,flags.2 as i64]);
                },
                3=>{
                    if p.len()!=1{return Err(INVALID);}let s=&mut self.rows[slot].state;
                    if s.has(SNAP)||!approx(s.v[4],p[0]) {
                        s.v[4]=f64::from(p[0] as f32);if s.has(SNAP)||(s.v[13]<=0.&&(s.v[1]-p[0]).abs()>0.5){s.v[1]=f64::from(p[0] as f32);s.v[9]=position_write_yaw(s.v[9]);}s.set(SETTLED,false);s.set(SLEEP,false);
                    }
                },
                // Approved Godot clip sink owns the actual sampler and facing
                // retarget. Refresh only these results, not a second clip timer.
                4=>{
                    if p.len()!=11||p[0].fract()!=0.||!(0.0..=22.0).contains(&p[0])||p[8]<=0.{return Err(INVALID);}
                    let s=&mut self.rows[slot].state;s.v[26]=p[0];s.v[22..26].copy_from_slice(&p[1..5]);s.set(FACING,p[5]!=0.);s.set(AIM,p[6]!=0.);s.set(MOUNT,p[7]!=0.);s.v[30]=p[8];s.set(SETTLED,p[9]!=0.);
                    if p[0]==5.{s.v[13]=0.;s.v[21]=0.;s.set(TRAVEL,false);}
                    if p[10]!=0.{s.set(SLEEP,false);}
                },
                5=>{
                    if !p.is_empty(){return Err(INVALID);}self.rows[slot].alive=false;self.lookup.remove(&id);
                    if self.rows.len()>self.lookup.len()*2+128 {
                        self.rows.retain(|r|r.alive);self.lookup.clear();
                        for (index,row) in self.rows.iter().enumerate(){self.lookup.insert(row.id,index);}
                    }
                },
                6=>{let replacement=State::parse(p)?;self.rows[slot].state=replacement;},
                // action selection: resolved action, changed, combatChanged,
                // fresh, commandSequence, secondaryClipAvailable.
                7=>{
                    if p.len()!=6||p.iter().any(|x|x.fract()!=0.)||!(0.0..=22.0).contains(&p[0]){return Err(INVALID);}
                    let s=&mut self.rows[slot].state;let mut action=s.aware(s.paced(p[0] as i64),p[1]!=0.);
                    let transient=[12,13,14,15,16,17,18,9,10,11,19,20,21].contains(&(s.v[26] as i64));
                    let stale=p[4]>=0.&&p[3]==0.&&[19,21].contains(&action);
                    if stale||!(p[3]!=0.||p[1]!=0.||(!transient&&(p[2]!=0.||p[4]<0.))||action==5){action=-1;}
                    if action==19&&p[3]!=0.&&p[5]!=0.{action=if s.v[28] as i64%2==0{19}else{20};s.v[28]+=1.;}
                    self.meta.clear();self.meta.extend([id,generation,epoch,map,sequence,action,((p[3]!=0.)&&[19,20,21].contains(&action)) as i64]);
                },
                8=>{
                    if !p.is_empty(){return Err(INVALID);}
                    let s=&self.rows[slot].state;
                    let action=match s.v[26] as i64 {
                        6=>7,8=>0,9=>10,13=>14,
                        12|15|16|17|18|19|20|22|11|21=>s.aware(if s.has(COMBAT){1}else{0},false),
                        _=>-1,
                    };
                    self.meta.clear();self.meta.extend([id,generation,epoch,map,sequence,action,0]);
                },
                _=>return Err(INVALID),
            }
        }
        self.sequence=sequence;
        if ![2,7,8].contains(&op){self.meta.clear();self.meta.extend([id,generation,epoch,map,sequence]);}
        self.values.clear();if let Some(slot)=self.lookup.get(&id){self.rows[*slot].state.write(&mut self.values,true);}Ok(())
    }
    fn tick(&mut self,epoch:i64,map:i64,frame:i64,dt:f64)->Result<(),i32>{
        if epoch!=self.epoch||map!=self.map||frame<=self.last_tick{return Err(STALE);}
        if !dt.is_finite()||dt<0.||dt>10.{return Err(INVALID);}
        self.meta.clear();self.values.clear();
        for row in &mut self.rows {
            if !row.alive||row.state.has(SETTLED)||row.state.has(SLEEP){continue;}
            let action=row.state.tick(dt);let offset=self.values.len();
            row.state.write(&mut self.values,false);
            self.meta.extend([row.id,row.generation,epoch,map,frame,offset as i64,action]);
        }
        self.last_tick=frame;Ok(())
    }
}

// Ordinary AnimationGate: shared group deltas, insertion order, empty-group
// clocks and stable membership. Mounted phase/pending clocks stay elsewhere.
#[derive(Default)]
struct Gate{tick:i64,delta:[f64;6],members:[Vec<(i64,i64)>;6],of:HashMap<i64,(i64,usize)>}
impl Gate {
    fn apply(&mut self,id:i64,generation:i64,tier:i64,stagger:bool)->Result<i64,i32>{
        if id<=0||generation<=0||!(0..=3).contains(&tier){return Err(INVALID);}
        if let Some((g,at))=self.of.get(&id).copied(){
            if g!=generation{return Err(STALE);}
            if (tier==1&&at<2)||(tier==3&&at>=2){return Ok(at as i64);}
            self.discard(id,generation)?;
        }
        if ![1,3].contains(&tier){return Ok(-1);}
        let range=if tier==1{0..2}else{2..6};let mut chosen=range.start;
        for at in range{if stagger&&self.members[at].len()<self.members[chosen].len(){chosen=at;}}
        self.members[chosen].push((id,generation));self.of.insert(id,(generation,chosen));Ok(chosen as i64)
    }
    fn discard(&mut self,id:i64,generation:i64)->Result<(),i32>{
        if let Some((g,at))=self.of.get(&id).copied(){
            if g!=generation{return Err(STALE);}self.members[at].retain(|x|x.0!=id);self.of.remove(&id);
        }Ok(())
    }
    fn advance(&mut self,dt:f64,meta:&mut Vec<i64>,values:&mut Vec<f64>)->Result<(),i32>{
        if !dt.is_finite()||!(0.0..=10.).contains(&dt){return Err(INVALID);}
        self.tick+=1;meta.clear();values.clear();
        for at in 0..6 {
            self.delta[at]+=dt;let stride=if at<2{2}else{4};let phase=if at<2{at}else{at-2};
            if (self.tick+phase as i64)%stride!=0{continue;}
            let step=self.delta[at];self.delta[at]=0.;
            for (id,g) in &self.members[at]{meta.extend([*id,*g,at as i64]);values.push(step);}
        }
        values.extend_from_slice(&self.delta);values.push(self.tick as f64);Ok(())
    }
}

// C ABI: opaque handles and borrowed output buffers valid until the next call.
// C++ copies both buffers before any Godot callback. Foreign-thread rejection is
// in the adapter; the Rust runtime has one main-thread owner.
fn guarded(f:impl FnOnce()->Result<(),i32>)->i32{match catch_unwind(AssertUnwindSafe(f)){Ok(Ok(()))=>0,Ok(Err(e))=>e,Err(_)=>INTERNAL}}
#[unsafe(no_mangle)]pub extern "C" fn rl_remote_create(epoch:i64)->*mut Remote{if epoch<1{return std::ptr::null_mut();}Box::into_raw(Box::new(Remote{epoch,last_tick:-1,..Remote::default()}))}
#[unsafe(no_mangle)]pub unsafe extern "C" fn rl_remote_destroy(p:*mut Remote){if !p.is_null(){unsafe{drop(Box::from_raw(p));}}}
#[unsafe(no_mangle)]pub unsafe extern "C" fn rl_remote_reset(p:*mut Remote,epoch:i64)->i32{guarded(||{let r=unsafe{p.as_mut()}.ok_or(INVALID)?;if epoch<=r.epoch{return Err(STALE);}*r=Remote{epoch,last_tick:-1,..Remote::default()};Ok(())})}
#[unsafe(no_mangle)]pub unsafe extern "C" fn rl_remote_event(p:*mut Remote,op:i64,id:i64,g:i64,epoch:i64,seq:i64,map:i64,values:*const f64,count:usize)->i32{guarded(||{if count>LIMIT+100||values.is_null()&&count>0{return Err(INVALID);}let values=if count==0{&[]}else{unsafe{slice::from_raw_parts(values,count)}};unsafe{p.as_mut()}.ok_or(INVALID)?.event(op,id,g,epoch,seq,map,values)})}
#[unsafe(no_mangle)]pub unsafe extern "C" fn rl_remote_tick(p:*mut Remote,epoch:i64,map:i64,frame:i64,dt:f64)->i32{guarded(||unsafe{p.as_mut()}.ok_or(INVALID)?.tick(epoch,map,frame,dt))}
#[unsafe(no_mangle)]pub unsafe extern "C" fn rl_remote_map(p:*mut Remote,epoch:i64,map:i64)->i32{guarded(||{let r=unsafe{p.as_mut()}.ok_or(INVALID)?;if epoch!=r.epoch||map<=r.map{return Err(STALE);}r.map=map;Ok(())})}
#[unsafe(no_mangle)]pub unsafe extern "C" fn rl_remote_gate(p:*mut Remote,op:i64,id:i64,g:i64,tier:i64,stagger:bool,dt:f64)->i64{
    match catch_unwind(AssertUnwindSafe(||{let r=unsafe{p.as_mut()}.ok_or(INVALID)?;match op{
        1=>r.gate.apply(id,g,tier,stagger),2=>{r.gate.discard(id,g)?;Ok(0)},3=>{r.gate.advance(dt,&mut r.meta,&mut r.values)?;Ok(0)},4=>{r.gate=Gate::default();Ok(0)},_=>Err(INVALID)
    }})){Ok(Ok(v))=>v,Ok(Err(e))=>-10-i64::from(e),Err(_)=>-13}
}
#[unsafe(no_mangle)]pub unsafe extern "C" fn rl_remote_outputs(p:*const Remote,meta:*mut *const i64,nm:*mut usize,values:*mut *const f64,nv:*mut usize)->i32{
    if p.is_null()||meta.is_null()||nm.is_null()||values.is_null()||nv.is_null(){return INVALID;}
    let r=unsafe{&*p};unsafe{*meta=r.meta.as_ptr();*nm=r.meta.len();*values=r.values.as_ptr();*nv=r.values.len();}0
}
#[unsafe(no_mangle)]pub unsafe extern "C" fn rl_remote_stats(p:*const Remote,output:*mut i64,count:usize)->i32{
    if p.is_null()||output.is_null()||count!=12{return INVALID;}
    let r=unsafe{&*p};let mut history_capacity=0;let mut history_values=0;
    for row in &r.rows{for h in row.state.histories.iter().chain(std::iter::once(&row.state.unconfirmed)){
        history_capacity+=h.capacity();history_values+=h.len();
    }}
    let bytes=r.rows.capacity()*std::mem::size_of::<Row>()+history_capacity*std::mem::size_of::<f32>()
        +r.meta.capacity()*std::mem::size_of::<i64>()+r.values.capacity()*std::mem::size_of::<f64>();
    let values=[r.epoch,r.map,r.sequence,r.lookup.len() as i64,r.rows.len() as i64,r.rows.capacity() as i64,
        history_values as i64,history_capacity as i64,r.gate.of.len() as i64,r.gate.tick,bytes as i64,
        r.rows.iter().filter(|row|row.alive&&!row.state.has(SETTLED)&&!row.state.has(SLEEP)).count() as i64];
    unsafe{std::ptr::copy_nonoverlapping(values.as_ptr(),output,count);}0
}

#[unsafe(no_mangle)]pub unsafe extern "C" fn rl_remote_classify(records:*const f64,count:usize,planes:*const f64,plane_count:usize,camera:*const f64,output:*mut i64)->i32{
    guarded(||{
        if count>LIMIT||plane_count>6||(count>0&&(records.is_null()||output.is_null()))
            ||(plane_count>0&&planes.is_null())||camera.is_null(){return Err(INVALID);}
        let records=if count==0{&[]}else{unsafe{slice::from_raw_parts(records,count*4)}};
        let planes=if plane_count==0{&[]}else{unsafe{slice::from_raw_parts(planes,plane_count*4)}};
        let camera=unsafe{slice::from_raw_parts(camera,3)};
        if !records.iter().chain(planes).chain(camera).all(|x|x.is_finite())
            ||records.chunks_exact(4).any(|r|r[3]<0.){return Err(INVALID);}
        // Match the supported engine's real_t=float geometry arithmetic.
        for (index,row) in records.chunks_exact(4).enumerate(){
            let a=[row[0] as f32,row[1] as f32,row[2] as f32];let mut tier=0;
            if !planes.is_empty(){
                if planes.chunks_exact(4).any(|p|f64::from((p[0] as f32*a[0]+p[1] as f32*a[1]+p[2] as f32*a[2])-p[3] as f32)>row[3]){tier=2;}
                else {let d=[a[0]-camera[0] as f32,a[1]-camera[1] as f32,a[2]-camera[2] as f32];if (d[0]*d[0]+d[1]*d[1]+d[2]*d[2]).sqrt()>45.{tier=1;}}
            }
            unsafe{*output.add(index)=tier;}
        }Ok(())
    })
}

#[cfg(test)]mod tests {
    use super::*;
    fn fixture()->Vec<f64>{let mut v=vec![0.;FIXED];v[14]=-1.;v[15]=0.6;v[17]=-1.;v[18]=1.;v[27]=-1.;v[29]=SETTLED as f64;v[30]=0.2;v[31]=1.;v[32]=6.;v[33]=9.;v[34]=0.6;v[35]=0.2;v[36]=12.;v[37]=1.25;v[38]=0.35;v[39]=1.25;v[40]=0.06;v[41]=1.1;v[42]=0.12;v[43]=0.15;v[46]=-1.;v.extend([0.;5]);v}
    fn runtime()->Remote{Remote{epoch:1,last_tick:-1,..Remote::default()}}
    fn motion(x:f64,arrival:f64,stamp:f64,command:f64,seq:f64)->Vec<f64>{let mut p=vec![x,0.,0.,0.,arrival,stamp,0.12,command,seq,0.,0.,1.,0.,command,0.2,0.,0.,0.];p.extend_from_slice(&fixture()[31..44]);p}
    #[test]fn all_gait_histories_and_full_transfer(){let mut r=runtime();r.event(1,7,1,1,1,0,&fixture()).unwrap();for i in 1..80{let p=motion((i%7)as f64,1000.+i as f64*200.,900.+i as f64*200.,if i%2==0{30.}else{0.},i as f64);r.event(2,7,1,1,i+1,0,&p).unwrap();}let mut full=Vec::new();r.rows[0].state.write(&mut full,true);let copy=State::parse(&full).unwrap();assert_eq!(copy.v,r.rows[0].state.v);assert_eq!(copy.histories,r.rows[0].state.histories);assert_eq!(copy.unconfirmed,r.rows[0].state.unconfirmed);}
    #[test]fn stamped_schedule_and_mount_floor(){
        let mut s=State::parse(&fixture()).unwrap();let mut p=motion(1.,1000.,900.,30.,1.);
        p[14]=0.04;p[15]=1.;s.movement(&p);
        // step(.900)+cadence(.040)+playout(.120)-arrival(1.000)=.060.
        // A fast floor permits shorter segments; it does not remove playout.
        assert!((s.v[13]-0.06).abs()<1e-9);assert_eq!(s.v[14],900.);
        let mut floor=State::parse(&fixture()).unwrap();p[6]=0.;floor.movement(&p);
        // Due is already past; distance/speed=.032, hence mount floor=.040.
        assert!((floor.v[13]-0.04).abs()<1e-9);
    }
    #[test]fn invalid_event_stale_generation_map_reset_are_atomic(){let mut r=runtime();r.event(1,7,1,1,1,0,&fixture()).unwrap();let before=r.rows[0].state.v;let mut p=motion(1.,1000.,900.,0.,1.);p[0]=f64::NAN;assert_eq!(r.event(2,7,1,1,2,0,&p),Err(INVALID));assert_eq!(r.rows[0].state.v,before);assert_eq!(r.sequence,1);r.event(5,7,1,1,2,0,&[]).unwrap();assert_eq!(r.event(1,7,1,1,3,0,&fixture()),Err(STALE));r.event(1,7,2,1,3,0,&fixture()).unwrap();assert_eq!(r.event(3,7,1,1,4,0,&[2.]),Err(STALE));assert_eq!(r.tick(1,1,1,0.1),Err(STALE));}
    #[test]fn coast_settles_and_death_does_not_replay(){let mut s=State::parse(&fixture()).unwrap();s.v[26]=2.;s.set(SETTLED,false);s.v[21]=0.05;assert_eq!(s.tick(0.1),0);s.v[26]=5.;assert_eq!(s.tick(0.1),-1);assert!(s.has(SLEEP));}
    #[test]fn gate_shared_empty_group_and_late_join_delta(){let mut g=Gate::default();let(mut m,mut v)=(Vec::new(),Vec::new());g.advance(0.1,&mut m,&mut v).unwrap();assert_eq!(g.apply(1,1,1,false),Ok(0));g.advance(0.2,&mut m,&mut v).unwrap();assert_eq!(m,[1,1,0]);assert!((v[0]-0.3).abs()<1e-12);assert_eq!(g.apply(2,2,1,true),Ok(1));g.discard(1,1).unwrap();assert_eq!(g.of[&2],(2,1));}
    #[test]fn stale_strike_and_alternating_primary(){let mut r=runtime();r.event(1,7,1,1,1,0,&fixture()).unwrap();r.event(7,7,1,1,2,0,&[19.,0.,0.,1.,3.,1.]).unwrap();assert_eq!(r.meta[5],19);r.event(7,7,1,1,3,0,&[19.,0.,0.,0.,3.,1.]).unwrap();assert_eq!(r.meta[5],-1);r.event(7,7,1,1,4,0,&[19.,0.,0.,1.,4.,1.]).unwrap();assert_eq!(r.meta[5],20);}
    #[test]fn antipodal_rotation_uses_godot_signed_tie(){
        assert_eq!(angle_delta(PI),-PI);assert_eq!(angle_delta(-PI),PI);
        assert!((rotate(0.,PI,0.1)+0.1).abs()<1e-12);
        assert!((rotate(0.,-PI,0.1)-0.1).abs()<1e-12);
        assert!((angle_delta(3.*PI)+PI).abs()<1e-12);
    }
    #[test]fn position_write_canonicalizes_before_turn_not_after_output(){
        let mut s=State::parse(&fixture()).unwrap();s.set(SETTLED,false);
        s.v[9]=f64::from((PI-0.01) as f32);s.v[10]=-PI+0.3;s.v[21]=1.;
        s.tick(0.005);
        // The setter just crossed +PI: that unwrapped value is observable.
        assert!(s.v[9]>PI);
        let first=s.v[9];s.tick(0.005);
        // Next global-position write canonicalizes before the next turn.
        assert!(s.v[9]<0.);assert!((angle_delta(s.v[9]-first)-0.06).abs()<0.000002);
        let mut dead=State::parse(&fixture()).unwrap();dead.v[9]=4.626912594;dead.v[26]=5.;
        dead.tick(0.016);assert!(dead.v[9]<0.);assert!(dead.has(SLEEP));
        let mut snap=State::parse(&fixture()).unwrap();snap.set(SNAP,true);snap.v[10]=4.;
        snap.tick(0.016);assert_eq!(snap.v[9],4.); // direct yaw setter remains authoritative
    }
    #[test]fn surface_yaw_readback_only_when_position_is_written(){
        for (duration,height,snap,writes) in [(0.,2.,false,true),(1.,2.,false,false),(0.,0.25,false,false),(0.,0.,false,false),(0.,0.,true,true)] {
            let mut state=fixture();state[9]=4.;state[13]=duration;state[29]=if snap{SNAP as f64}else{0.};
            let mut r=runtime();r.event(1,7,1,1,1,0,&state).unwrap();r.event(3,7,1,1,2,0,&[height]).unwrap();
            if writes {assert!(r.rows[0].state.v[9]<0.);}else{assert_eq!(r.rows[0].state.v[9],4.);}
        }
    }
    #[test]fn classify_full_half_paused_blind_and_invalid_whole_output(){unsafe{
        let records=[0.,0.,0.,1.,0.,0.,-50.,1.,20.,0.,0.,1.];let planes=[1.,0.,0.,10.];let camera=[0.,0.,0.];let mut out=[9;3];
        assert_eq!(rl_remote_classify(records.as_ptr(),3,planes.as_ptr(),1,camera.as_ptr(),out.as_mut_ptr()),0);assert_eq!(out,[0,1,2]);
        assert_eq!(rl_remote_classify(records.as_ptr(),3,std::ptr::null(),0,camera.as_ptr(),out.as_mut_ptr()),0);assert_eq!(out,[0,0,0]);
        let invalid=[0.,0.,0.,1.,f64::NAN,0.,0.,1.];out=[9;3];assert_eq!(rl_remote_classify(invalid.as_ptr(),2,planes.as_ptr(),1,camera.as_ptr(),out.as_mut_ptr()),INVALID);assert_eq!(out,[9;3]);
    }}
}
