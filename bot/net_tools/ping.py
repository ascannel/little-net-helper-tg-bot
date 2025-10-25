import re
import subprocess
from dataclasses import dataclass

@dataclass
class PingResult:
    ok: bool
    transmitted: int
    received: int
    loss_pct: float
    min_ms: float | None
    avg_ms: float | None
    max_ms: float | None
    stddev_ms: float | None
    raw_tail: str

def run(host: str, count: int = 10, deadline_s: int | None = None, per_reply_timeout_s: int = 2) -> PingResult:
    """
    Выполняет `ping -c <count> -n -W <per_reply_timeout> [-w <deadline>] <host>`
    Работает на Linux/WSL. Без прав root.
    """
    args = ["ping", "-c", str(count), "-n", "-W", str(per_reply_timeout_s)]
    if deadline_s:
        args += ["-w", str(deadline_s)]
    args.append(host)

    try:
        proc = subprocess.run(
            args,
            capture_output=True,
            text=True,
            timeout=max(5, count * (per_reply_timeout_s + 1)),
            check=False,
        )
    except Exception as e:
        return PingResult(
            ok=False, transmitted=0, received=0, loss_pct=100.0,
            min_ms=None, avg_ms=None, max_ms=None, stddev_ms=None,
            raw_tail=f"ping failed: {e}"
        )

    out = (proc.stdout or "") + (("\n" + proc.stderr) if proc.stderr else "")
    tail = "\n".join(out.strip().splitlines()[-6:])  # оставим хвост (stat + rtt)

    # 10 packets transmitted, 10 received, 0% packet loss, time 9014ms
    # rtt min/avg/max/mdev = 29.998/30.237/30.745/0.221 ms
    m1 = re.search(
        r"(?P<tx>\d+)\s+packets?\s+transmitted,\s+(?P<rx>\d+)\s+(?:packets?\s+)?received,\s+(?P<loss>[\d.]+)%\s+packet\s+loss",
        out, re.IGNORECASE
    )
    m2 = re.search(
        r"rtt\s+min/avg/max/(?:mdev|stddev)\s*=\s*(?P<min>[\d.]+)/(?P<avg>[\d.]+)/(?P<max>[\d.]+)/(?P<std>[\d.]+)",
        out, re.IGNORECASE
    )

    if not m1:
        return PingResult(
            ok=False, transmitted=0, received=0, loss_pct=100.0,
            min_ms=None, avg_ms=None, max_ms=None, stddev_ms=None,
            raw_tail=tail or out[-500:]
        )

    tx = int(m1.group("tx"))
    rx = int(m1.group("rx"))
    loss = float(m1.group("loss"))

    min_ms = avg_ms = max_ms = stddev_ms = None
    if m2:
        min_ms = float(m2.group("min"))
        avg_ms = float(m2.group("avg"))
        max_ms = float(m2.group("max"))
        stddev_ms = float(m2.group("std"))

    return PingResult(
        ok=rx > 0 and loss < 100.0,
        transmitted=tx,
        received=rx,
        loss_pct=loss,
        min_ms=min_ms,
        avg_ms=avg_ms,
        max_ms=max_ms,
        stddev_ms=stddev_ms,
        raw_tail=tail,
    )