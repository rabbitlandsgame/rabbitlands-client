"""Machine-readable progress for the long continent build stages.

The stage runner and the composer write one small record beside the other
generated ledgers, so a separate editor can follow a running build without
parsing the console:

    {"stage": "compose", "step": "roads and routing", "fraction": 0.25,
     "status": "running", "startedAt": "2026-09-15T20:12:31.004Z",
     "updatedAt": "2026-09-15T20:18:02.560Z", "exit": null, "pid": 8124}

Every record replaces the file atomically, so a reader never sees half a write.
Progress is reporting, never a build dependency: each public call catches its
own failures (a locked file, a read-only directory, a full disk) and warns
instead of aborting a thirteen-minute stage.
"""
from __future__ import annotations
from datetime import datetime,timezone
import json
import os
from pathlib import Path
import sys
import tempfile

KEYS=('stage','step','fraction','status','startedAt','updatedAt','exit','pid')
STATUSES=('running','done','failed')


def now():
    """This instant in UTC ISO-8601, to the millisecond."""
    return datetime.now(timezone.utc).isoformat(timespec='milliseconds').replace('+00:00','Z')


class Progress:
    """One progress record. An inert record (path None) writes nothing."""

    def __init__(self,path):
        self.path=Path(path) if path is not None else None
        self.stage='';self.step_name='';self.fraction=0.;self.status='running'
        self.started=None;self.exit=None;self.steps=None;self.done=0

    def attach(self,path):
        """Point an inert record at a file once the output directory is known."""
        self.path=Path(path) if path is not None else None;return self

    def watch(self):
        """Record a failed stage if the build dies on an uncaught exception."""
        previous=sys.excepthook
        def report(kind,value,trace):
            self.finish(getattr(value,'returncode',1) or 1);previous(kind,value,trace)
        sys.excepthook=report;return self

    def start(self,stage,steps=None):
        """Begin a stage; steps becomes the default total for later step calls."""
        self.stage=str(stage);self.steps=steps;self.done=0
        self.step_name='';self.fraction=0.;self.status='running';self.exit=None
        self.started=self.started or now();self._write()

    def step(self,name,done=None,total=None):
        """Report a named step, fraction done/total clamped to 0..1.

        done defaults to a counter of the steps reported so far and total to the
        count given to start(); a missing or zero total reads as no progress.
        """
        self.done=self.done+1 if done is None else done
        total=self.steps if total is None else total
        self.step_name=str(name)
        self.fraction=min(1.,max(0.,self.done/total)) if total else 0.
        self.status='running';self._write()

    def finish(self,exit_code=0):
        """Close the stage: done for exit code 0, failed for anything else."""
        self.exit=int(exit_code);self.status='done' if self.exit==0 else 'failed'
        if self.exit==0:self.fraction=1.
        self._write()

    def record(self):
        """The record as written; startedAt is this record's first written stage."""
        return {'stage':self.stage,'step':self.step_name,
            'fraction':round(float(min(1.,max(0.,self.fraction))),6),'status':self.status,
            'startedAt':self.started or now(),'updatedAt':now(),'exit':self.exit,'pid':os.getpid()}

    def _write(self):
        if self.path is None:return
        try:
            self.path.parent.mkdir(parents=True,exist_ok=True)
            handle,temporary=tempfile.mkstemp(dir=str(self.path.parent),prefix=self.path.name+'.',suffix='.tmp')
            try:
                with os.fdopen(handle,'w',encoding='utf-8',newline='\n') as stream:
                    json.dump(self.record(),stream,indent=2);stream.write('\n')
                os.replace(temporary,self.path)
            except BaseException:
                Path(temporary).unlink(missing_ok=True);raise
        except Exception as error:
            print(f'Warning: build progress not written to {self.path}: {error}',flush=True)
