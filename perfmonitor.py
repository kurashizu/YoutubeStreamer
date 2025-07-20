import psutil
import time
import threading

class PerfMon:
    def __init__(self, interval: int = 1):

        self.interval = interval
        self._last_net_up = 0
        self._last_net_down = 0

        self.performance_string = "Time: dd/mm/yy HH:MM:SS | CPU: xx% | MEM: xx/xx GB | SWAP: xx/xx GB | NET U-xxkbps D-xx (K/s)"
        self.lock = threading.Lock()

        threading.Thread(target=self._worker_performance_string, daemon=True).start()

    def _worker_performance_string(self) -> str:
        # Time: dd/mm/yy HH:MM:SS | CPU: xx% | MEM: xx/xx GB | SWAP: xx/xx GB | NET U-xxkbps D-xxK/s
        while True:
            cpu_usage = psutil.cpu_percent(interval=self.interval)
            mem = psutil.virtual_memory()
            mem_usage = mem.percent
            mem_total = mem.total / (1024 ** 3)  # Convert to GB
            mem_used = mem.used / (1024 ** 3)  # Convert to GB
            swap = psutil.swap_memory()
            swap_usage = swap.percent
            swap_total = swap.total / (1024 ** 3)  # Convert to GB
            swap_used = swap.used / (1024 ** 3)  # Convert to GB
            net_io = psutil.net_io_counters()
            global _last_net_up, _last_net_down
            net_up = (net_io.bytes_sent - self._last_net_up) / 1024
            net_down = (net_io.bytes_recv - self._last_net_down) / 1024
            self._last_net_up = net_io.bytes_sent
            self._last_net_down = net_io.bytes_recv
            
            with self.lock:
                self.performance_string = f"Time: {time.strftime('%d/%m/%y %H:%M:%S', time.localtime())} | CPU: {cpu_usage}% | MEM: {mem_used:.2f}/{mem_total:.2f} GB | SWAP: {swap_used:.2f}/{swap_total:.2f} GB | NET up-{net_up:.2f} down-{net_down:.2f} (K/s)"

    def get_performance_string(self) -> str:
        with self.lock:
            result = self.performance_string
        return result
        
if __name__ == "__main__":
    perfmon = PerfMon()
    while True:
        print(perfmon.get_performance_string())
        time.sleep(1)