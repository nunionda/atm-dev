"""
포트 점검 및 프로세스 관리 유틸리티.

API 서버(uvicorn) 시작 전 포트 충돌을 감지하고,
기존 프로세스를 자동으로 정리하는 기능을 제공한다.
"""

from __future__ import annotations

import os
import signal
import socket
import subprocess
import time


def is_port_in_use(port: int, host: str = "0.0.0.0") -> bool:
    """TCP 포트가 현재 사용 중인지 확인한다.

    socket.bind()를 시도하여 포트 가용성을 판단한다.
    uvicorn이 bind할 수 있는지와 동일한 조건으로 테스트.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(1)
        try:
            s.bind((host, port))
            return False
        except OSError:
            return True


def find_pid_on_port(port: int) -> int | None:
    """지정 포트에서 LISTEN 중인 프로세스의 PID를 조회한다.

    macOS/Linux의 lsof 명령을 사용한다.
    프로세스를 찾지 못하거나 명령 실패 시 None 반환.
    """
    try:
        result = subprocess.run(
            ["lsof", "-ti", f":{port}", "-sTCP:LISTEN"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            pid_str = result.stdout.strip().split("\n")[0]
            return int(pid_str)
    except (subprocess.TimeoutExpired, FileNotFoundError, ValueError):
        pass
    return None


def kill_process_on_port(port: int, graceful_timeout: float = 5.0) -> bool:
    """포트를 점유한 프로세스를 찾아 종료한다.

    전략:
    1. lsof로 PID 조회
    2. SIGTERM 전송 (graceful shutdown 기회 부여)
    3. graceful_timeout 초 대기
    4. 미종료 시 SIGKILL 강제 종료
    5. 포트 해제 확인

    Returns:
        True: 포트가 해제됨, False: 해제 실패
    """
    pid = find_pid_on_port(port)
    if pid is None:
        print(f"  [port_manager] 포트 {port}에서 프로세스를 찾지 못했습니다")
        return False

    # 자기 자신 보호
    if pid == os.getpid():
        print(f"  [port_manager] 포트 {port}은 현재 프로세스(PID {pid})가 점유 중, 건너뜀")
        return False

    proc_name = _get_process_name(pid)
    print(f"  [port_manager] 포트 {port} 점유: PID {pid} ({proc_name})")

    # Step 1: SIGTERM (graceful)
    try:
        print(f"  [port_manager] PID {pid}에 SIGTERM 전송...")
        os.kill(pid, signal.SIGTERM)
    except PermissionError:
        print(f"  [port_manager] 권한 부족: PID {pid}를 종료할 수 없습니다. sudo로 실행하세요.")
        return False
    except ProcessLookupError:
        print(f"  [port_manager] PID {pid}는 이미 종료됨")
        return True

    # Step 2: 종료 대기
    deadline = time.monotonic() + graceful_timeout
    while time.monotonic() < deadline:
        if not _is_process_alive(pid):
            print(f"  [port_manager] PID {pid} 정상 종료됨")
            time.sleep(0.3)
            return True
        time.sleep(0.2)

    # Step 3: SIGKILL (강제)
    print(f"  [port_manager] PID {pid}가 {graceful_timeout}초 내 미종료, SIGKILL 전송...")
    try:
        os.kill(pid, signal.SIGKILL)
        time.sleep(0.5)
    except ProcessLookupError:
        pass

    if not _is_process_alive(pid):
        print(f"  [port_manager] PID {pid} 강제 종료 완료")
        return True

    print(f"  [port_manager] PID {pid} 종료 실패")
    return False


def _is_process_alive(pid: int) -> bool:
    """프로세스 존재 여부를 확인한다 (signal 0 기법)."""
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def _get_process_name(pid: int) -> str:
    """PID로부터 프로세스 이름을 조회한다."""
    try:
        result = subprocess.run(
            ["ps", "-p", str(pid), "-o", "comm="],
            capture_output=True,
            text=True,
            timeout=3,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    return "unknown"
