# simulator_full.py
"""
Simulador de Sistemas Operativos - Python
Cubre:
 - Simulación de procesos con prioridad, duración, acceso a archivos
 - Planificadores: Round Robin, SJF (preemptivo/non-preemptivo), Prioridad
 - Gestión de memoria: paginación por demanda con FIFO y LRU
 - Gestión de archivos: acceso concurrente con mutex (bloqueo)
 - Registro de métrricas y casos de prueba
"""

from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple
from collections import deque, defaultdict
import heapq
import random
import time

# -------------------------
# Estructura Process
# -------------------------
@dataclass
class IOOperation:
    time: int
    filename: str
    op: str  # 'r' o 'w'
    duration: int = 1  # tiempo que dura la operacion (simulado)

@dataclass
class Process:
    pid: int
    arrival: int
    total_cpu: int
    priority: int = 0
    pages: int = 1
    io_ops: List[IOOperation] = field(default_factory=list)
    remaining: int = field(init=False)
    start_time: Optional[int] = None
    finish_time: Optional[int] = None
    waiting_time: int = 0
    last_run_tick: Optional[int] = None
    page_table: Dict[int, bool] = field(init=False)  # page->present?

    def __post_init__(self):
        self.remaining = self.total_cpu
        self.page_table = {i: False for i in range(self.pages)}

# -------------------------
# Memory Manager
# -------------------------
class MemoryManager:
    def __init__(self, num_frames:int=4, replacement='FIFO'):
        self.num_frames = num_frames
        self.replacement = replacement.upper()
        self.frames: List[Tuple[int,int,int]] = []  # list of (frame_id, pid, page)
        self.frame_map = {}  # (pid,page) -> frame_id
        self.fifo_queue = deque()
        self.time = 0
        self.last_used = {}  # (pid,page)->last_tick for LRU
        self.page_faults = defaultdict(int)

    def access_page(self, pid:int, page:int, tick:int) -> bool:
        """Return True if page present; if not, handle page fault and load page."""
        self.time = tick
        key = (pid,page)
        if key in self.frame_map:
            # present
            self.last_used[key] = tick
            return True
        # page fault
        self.page_faults[pid] += 1
        self.load_page(pid, page, tick)
        return False

    def load_page(self, pid:int, page:int, tick:int):
        key = (pid,page)
        if len(self.frames) < self.num_frames:
            frame_id = len(self.frames)
            self.frames.append((frame_id, pid, page))
            self.frame_map[key] = frame_id
            self.fifo_queue.append(key)
            self.last_used[key] = tick
            return
        # need replacement
        if self.replacement == 'FIFO':
            victim = self.fifo_queue.popleft()
        elif self.replacement == 'LRU':
            # choose key with smallest last_used
            victim = min(self.last_used.items(), key=lambda kv: kv[1])[0]
            # remove victim from fifo queue if present
            try:
                self.fifo_queue.remove(victim)
            except ValueError:
                pass
        else:
            victim = self.fifo_queue.popleft()

        # evict
        victim_frame = self.frame_map.pop(victim)
        # replace in frames list
        for i,(fid,p,v) in enumerate(self.frames):
            if fid == victim_frame:
                self.frames[i] = (fid, pid, page)
                break
        # update mappings
        self.frame_map[key] = victim_frame
        self.fifo_queue.append(key)
        self.last_used.pop(victim, None)
        self.last_used[key] = tick

    def stats(self):
        return {
            'frames': list(self.frames),
            'page_faults': dict(self.page_faults),
            'num_frames': self.num_frames,
            'replacement': self.replacement
        }

# -------------------------
# File System Simulator
# -------------------------
class FileSimulator:
    def __init__(self):
        self.locks = {}  # filename -> pid who holds lock
        self.waiting = defaultdict(deque)  # filename -> deque of (pid,op,duration)
        self.conflicts = 0
        self.log = []

    def request(self, pid:int, filename:str, op:str, tick:int, duration:int=1):
        """If file free -> grant lock (exclusive) for duration (simulated by returning a release tick).
           If busy -> add to waiting queue and count conflict. Return a tuple (granted:bool, release_tick or None)."""
        if filename not in self.locks:
            self.locks[filename] = (pid, tick+duration)
            self.log.append((tick, pid, filename, op, 'granted'))
            return True, tick+duration
        else:
            # someone holds it
            self.waiting[filename].append((pid, op, duration))
            self.conflicts += 1
            self.log.append((tick, pid, filename, op, 'queued'))
            return False, None

    def release_expired(self, tick:int):
        """Release locks whose time expired and grant to next in queue if any."""
        to_release = [fname for fname,(pid,release) in self.locks.items() if release <= tick]
        for fname in to_release:
            self.locks.pop(fname, None)
            if self.waiting[fname]:
                pid,op,duration = self.waiting[fname].popleft()
                self.locks[fname] = (pid, tick+duration)
                self.log.append((tick, pid, fname, op, 'granted_from_queue'))

    def stats(self):
        return {'conflicts': self.conflicts, 'locks': dict(self.locks), 'waiting': {k:len(v) for k,v in self.waiting.items()}}

# -------------------------
# Scheduler implementations
# -------------------------
class SchedulerBase:
    def add_process(self, proc:Process): raise NotImplementedError
    def tick(self, current_tick:int) -> Optional[Process]: raise NotImplementedError
    def has_ready(self) -> bool: raise NotImplementedError

class RoundRobinScheduler(SchedulerBase):
    def __init__(self, quantum:int=2):
        self.quantum = quantum
        self.queue = deque()
        self.current_quantum_left = {}
        self.running: Optional[Process] = None
        self.last_run_pid = None
        self.pid_to_quantum = {}

    def add_process(self, proc:Process):
        self.queue.append(proc)

    def tick(self, current_tick:int) -> Optional[Process]:
        if not self.queue:
            return None
        proc = self.queue.popleft()
        return proc

    def has_ready(self) -> bool:
        return len(self.queue) > 0

class SJFScheduler(SchedulerBase):
    def __init__(self, preemptive=False):
        self.preemptive = preemptive
        # min-heap by remaining cpu
        self.heap = []

    def add_process(self, proc:Process):
        heapq.heappush(self.heap, (proc.remaining, proc.arrival, proc.pid, proc))

    def tick(self, current_tick:int) -> Optional[Process]:
        if not self.heap:
            return None
        _,_,_,proc = heapq.heappop(self.heap)
        return proc

    def has_ready(self) -> bool:
        return len(self.heap) > 0

class PriorityScheduler(SchedulerBase):
    def __init__(self, higher_value_higher_priority=False):
        # If higher_value_higher_priority True -> larger number = higher priority
        self.higher_value = higher_value_higher_priority
        self.heap = []

    def add_process(self, proc:Process):
        # we use negative priority if higher_value is True to make heapq pop highest priority
        key = -proc.priority if self.higher_value else proc.priority
        heapq.heappush(self.heap, (key, proc.arrival, proc.pid, proc))

    def tick(self, current_tick:int) -> Optional[Process]:
        if not self.heap:
            return None
        _,_,_,proc = heapq.heappop(self.heap)
        return proc

    def has_ready(self) -> bool:
        return len(self.heap) > 0

# -------------------------
# Simulator
# -------------------------
class Simulator:
    def __init__(self, scheduler:SchedulerBase, mem_manager:MemoryManager, fs:FileSimulator, quantum:int=2):
        self.scheduler = scheduler
        self.mem = mem_manager
        self.fs = fs
        self.quantum = quantum
        self.time = 0
        self.all_processes: Dict[int,Process] = {}
        self.ready_list = []
        self.finished = []
        self.metrics = {
            'cpu_busy_ticks': 0,
            'total_ticks': 0
        }

    def add_process(self, proc:Process):
        self.all_processes[proc.pid] = proc
        self.ready_list.append(proc)

    def run(self, max_ticks:int=1000):
        # Sort by arrival
        self.ready_list.sort(key=lambda p: p.arrival)
        pending = deque(self.ready_list)
        running_proc: Optional[Process] = None
        rr_quantum_left = self.quantum
        while self.time < max_ticks and (pending or self.scheduler.has_ready() or running_proc):
            # bring arrivals into scheduler
            while pending and pending[0].arrival <= self.time:
                p = pending.popleft()
                self.scheduler.add_process(p)
            # release expired file locks
            self.fs.release_expired(self.time)

            # select process to run
            if running_proc is None:
                proc = self.scheduler.tick(self.time)
                if proc:
                    running_proc = proc
                    if proc.start_time is None:
                        proc.start_time = self.time
                    rr_quantum_left = self.quantum
            else:
                # continue running current proc if RR quantum not exhausted (we keep simple: one tick per loop)
                proc = running_proc

            if proc:
                # simulate memory access: randomly access a page each tick
                page = random.randrange(0, proc.pages)
                present = self.mem.access_page(proc.pid, page, self.time)
                if not present:
                    # page fault handled inside mem; assume servicing takes 1 tick penalty
                    # we model penalty by consuming this tick but not decreasing cpu remaining
                    self.time += 1
                    self.metrics['total_ticks'] += 1
                    # after loading, continue to next loop
                    continue

                # check if there's an IO op scheduled at this tick
                io_now = [io for io in proc.io_ops if io.time == self.time]
                if io_now:
                    # attempt to request file lock for each io
                    for io in io_now:
                        granted, release_tick = self.fs.request(proc.pid, io.filename, io.op, self.time, duration=io.duration)
                        if not granted:
                            # process blocked: push back to scheduler and break
                            # record waiting - we simulate that it waits until lock is granted
                            proc.waiting_time += 1
                            # do not progress CPU for this process this tick
                            # put it back to scheduler queue for future
                            self.scheduler.add_process(proc)
                            running_proc = None
                            proc = None
                            break
                        else:
                            # if granted, we simulate IO taking io.duration ticks (simple model)
                            proc.remaining -= io.duration  # treat io duration as CPU consumption for simplicity
                            self.time += io.duration
                    if proc is None:
                        continue

                # execute one tick of CPU
                proc.remaining -= 1
                self.metrics['cpu_busy_ticks'] += 1
                self.metrics['total_ticks'] += 1
                self.time += 1

                # check finish
                if proc.remaining <= 0:
                    proc.finish_time = self.time
                    self.finished.append(proc)
                    running_proc = None
                else:
                    # quantum handling for RR: re-queue after quantum ticks
                    rr_quantum_left -= 1
                    if isinstance(self.scheduler, RoundRobinScheduler):
                        if rr_quantum_left <= 0:
                            # requeue
                            self.scheduler.add_process(proc)
                            running_proc = None
            else:
                # idle tick
                self.time += 1
                self.metrics['total_ticks'] += 1

        # After run, compute metrics
        results = self.compute_metrics()
        return results

    def compute_metrics(self):
        n = len(self.finished)
        total_wait = 0
        total_turnaround = 0
        for p in self.finished:
            turnaround = p.finish_time - p.arrival if p.finish_time is not None else 0
            waiting = (turnaround - p.total_cpu)
            p.waiting_time = waiting if waiting >= 0 else 0
            total_wait += p.waiting_time
            total_turnaround += turnaround
        avg_wait = total_wait / n if n else 0
        avg_turnaround = total_turnaround / n if n else 0
        cpu_util = (self.metrics['cpu_busy_ticks'] / max(1, self.metrics['total_ticks'])) * 100
        mem_stats = self.mem.stats()
        fs_stats = self.fs.stats()
        return {
            'finished_count': n,
            'avg_waiting_time': avg_wait,
            'avg_turnaround_time': avg_turnaround,
            'cpu_utilization_percent': cpu_util,
            'page_faults': mem_stats['page_faults'],
            'mem_frames': mem_stats['frames'],
            'file_conflicts': fs_stats['conflicts'],
            'time_elapsed': self.time
        }

# -------------------------
# Utilities: create sample workload and tests
# -------------------------
def sample_workload():
    # Create processes with varied attributes
    procs = [
        Process(pid=1, arrival=0, total_cpu=10, priority=2, pages=3,
                io_ops=[IOOperation(time=3, filename='fileA', op='r', duration=2)]),
        Process(pid=2, arrival=1, total_cpu=6, priority=5, pages=2,
                io_ops=[IOOperation(time=2, filename='fileA', op='w', duration=2)]),
        Process(pid=3, arrival=2, total_cpu=8, priority=1, pages=4,
                io_ops=[]),
        Process(pid=4, arrival=3, total_cpu=4, priority=3, pages=1,
                io_ops=[IOOperation(time=4, filename='fileB', op='r', duration=1)]),
    ]
    return procs

def run_demo():
    print("== Simulador Demo: RR quantum=2, mem frames=3, replacement=LRU ==")
    mem = MemoryManager(num_frames=3, replacement='LRU')
    fs = FileSimulator()
    sched = RoundRobinScheduler(quantum=2)
    sim = Simulator(scheduler=sched, mem_manager=mem, fs=fs, quantum=2)
    for p in sample_workload():
        sim.add_process(p)
    results = sim.run(max_ticks=200)
    print("Resultados:", results)
    print("Logs FS:", fs.log)
    print("Frames:", mem.frames)
    print("Page faults por pid:", mem.page_faults)

if __name__ == "__main__":
    run_demo()
