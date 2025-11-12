#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
gcode_sender_fixed.py  (compat + fast-pause version)

功能要点：
- 固件级快速暂停/恢复（Prusa: M601/M602；Marlin: M410/M24/M25；none）
- 兼容老接口/属性：state、pause()、resume()、stop()、start_file_print()、
  start_local_file_print()、print_file()、get_progress()、is_bed_heat_complete()
- 新增：is_hotend_heat_complete()；get_progress() 永远返回所需键

依赖：pip install requests
"""

import os
import json
import logging
from enum import Enum
from typing import Optional, Dict, Any

import requests


# -------------------- Logger --------------------
logger = logging.getLogger(__name__)
if not logger.handlers:
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s - %(levelname)s - %(message)s")


# -------------------- States --------------------
class PrinterState(Enum):
    UNKNOWN  = 0
    READY    = 1
    IDLE     = 1  # alias for READY（为兼容旧代码）
    PRINTING = 2
    PAUSED   = 3
    ERROR    = 4


# -------------------- Sender --------------------
class GCodeSender:
    """
    OctoPrint 控制封装（固件级快速暂停 + 老接口兼容）
    """
    def __init__(self,
                 base_url: str,
                 api_key: str,
                 firmware_mode: str = "prusa",
                 session: Optional[requests.Session] = None,
                 timeout_s: float = 6.0,
                 bed_tolerance_c: float = 3.0) -> None:
        """
        base_url     : OctoPrint 根地址，如 http://octopi.local
        api_key      : OctoPrint API Key
        firmware_mode: 'prusa' | 'marlin_quickstop' | 'marlin_sd' | 'none'
        timeout_s    : HTTP 超时时间
        bed_tolerance_c : 判断热床到温容差（°C）
        """
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.firmware_mode = firmware_mode.lower().strip()
        self.timeout_s = float(timeout_s)
        self.bed_tol = float(bed_tolerance_c)

        self.session = session or requests.Session()
        self.session.headers.update({
            "X-Api-Key": self.api_key,
            "Content-Type": "application/json"
        })

        # 上传用（multipart 由 requests 自动设定）
        self.upload_session = requests.Session()
        self.upload_session.headers.update({"X-Api-Key": self.api_key})

        self.logger = logger
        self._cached_state: PrinterState = PrinterState.UNKNOWN
        try:
            self._cached_state = self.get_state()
        except Exception:
            pass

    # ---------- 基础 HTTP ----------
    def _post(self, path: str, payload: Optional[Dict[str, Any]] = None,
              json_mode: bool = True) -> requests.Response:
        url = f"{self.base_url}{path}"
        if json_mode:
            return self.session.post(url,
                                     data=json.dumps(payload) if payload is not None else None,
                                     timeout=self.timeout_s)
        else:
            return self.session.post(url, data=payload, timeout=self.timeout_s)

    def _get(self, path: str) -> requests.Response:
        url = f"{self.base_url}{path}"
        return self.session.get(url, timeout=self.timeout_s)

    # ---------- 立即发送 G-code ----------
    def send_gcode_now(self, lines) -> bool:
        """
        立即向固件发送一组G-code（不经文件队列）。
        lines: str 或 [str, ...]
        """
        try:
            commands = [lines] if isinstance(lines, str) else list(lines)
            url = f"{self.base_url}/api/printer/command"
            resp = self.session.post(url, json={"commands": commands},
                                     timeout=self.timeout_s)
            if resp.status_code not in (204, 200):
                self.logger.warning(f"[GCODE] {url} -> {resp.status_code}: {resp.text}")
                return False
            return True
        except Exception as e:
            self.logger.error(f"[GCODE] send_gcode_now failed: {e}")
            return False

    # ---------- 状态 ----------
    def get_state(self) -> PrinterState:
        """
        综合 /api/job 与 /api/printer，返回 PrinterState，并更新缓存。
        """
        try:
            job = self._get("/api/job")
            if job.status_code == 200:
                j = job.json()
                st = str(j.get("state", "")).lower()
                if "printing" in st:
                    self._cached_state = PrinterState.PRINTING
                    return self._cached_state
                if "paused" in st:
                    self._cached_state = PrinterState.PAUSED
                    return self._cached_state
                if "operational" in st or "ready" in st:
                    self._cached_state = PrinterState.READY
                    return self._cached_state

            pr = self._get("/api/printer")
            if pr.status_code == 200:
                p = pr.json()
                flags = p.get("state", {}).get("flags", {})
                if flags.get("printing", False):
                    self._cached_state = PrinterState.PRINTING
                elif flags.get("paused", False):
                    self._cached_state = PrinterState.PAUSED
                elif flags.get("operational", False):
                    self._cached_state = PrinterState.READY
                else:
                    self._cached_state = PrinterState.UNKNOWN
                return self._cached_state

            self._cached_state = PrinterState.UNKNOWN
            return self._cached_state
        except Exception as e:
            self.logger.error(f"[STATE] get_state failed: {e}")
            self._cached_state = PrinterState.ERROR
            return self._cached_state

    @property
    def state(self) -> PrinterState:
        """兼容旧属性：直接读取当前状态。"""
        return self.get_state()

    # ---------- 上传并打印 ----------
    def start_print(self, file_path: str) -> bool:
        """上传本地 G-code 并立即打印。"""
        try:
            if not os.path.isfile(file_path):
                self.logger.error(f"[PRINT] File not found: {file_path}")
                return False
            filename = os.path.basename(file_path)
            url = f"{self.base_url}/api/files/local"
            with open(file_path, "rb") as f:
                files = {"file": (filename, f, "application/octet-stream")}
                data = {"select": "true", "print": "true"}
                resp = self.upload_session.post(url, files=files, data=data,
                                                timeout=max(30.0, self.timeout_s))
            if resp.status_code not in (201, 204):
                self.logger.error(f"[PRINT] upload/print failed {resp.status_code}: {resp.text}")
                return False
            self.logger.info(f"[PRINT] Upload & print started: {filename}")
            self._cached_state = PrinterState.PRINTING
            return True
        except Exception as e:
            self.logger.error(f"[PRINT] start_print failed: {e}")
            return False

    # ---- 兼容：旧方法名别名 ----
    def print_file(self, file_path: str) -> bool:
        return self.start_print(file_path)

    def start_file_print(self, file_path: str) -> bool:
        return self.start_print(file_path)

    def start_local_file_print(self, file_path: str) -> bool:
        return self.start_print(file_path)

    # ---------- 停止 ----------
    def stop_print(self) -> bool:
        """取消当前打印任务。"""
        try:
            r = self._post("/api/job", {"command": "cancel"})
            if r.status_code not in (204, 200):
                self.logger.warning(f"[STOP] cancel returned {r.status_code}: {r.text}")
                return False
            self.logger.info("[STOP] Print canceled.")
            self._cached_state = PrinterState.READY
            return True
        except Exception as e:
            self.logger.error(f"[STOP] stop_print failed: {e}")
            return False

    # ---- 兼容：旧方法名 'stop' ----
    def stop(self) -> bool:
        return self.stop_print()

    # ---------- 固件级 暂停/恢复 ----------
    def _firmware_pause(self) -> bool:
        mode = self.firmware_mode
        if mode == "none":
            return True
        if mode == "prusa":
            return self.send_gcode_now("M601")
        if mode == "marlin_quickstop":
            return self.send_gcode_now("M410")  # 立停，较“生硬”
        if mode == "marlin_sd":
            return self.send_gcode_now("M25")
        return True

    def _firmware_resume(self) -> bool:
        mode = self.firmware_mode
        if mode == "none":
            return True
        if mode == "prusa":
            return self.send_gcode_now("M602")
        if mode == "marlin_quickstop":
            return True  # 主机继续推流；这里只同步 UI
        if mode == "marlin_sd":
            return self.send_gcode_now("M24")
        return True

    # ---------- 暂停 / 恢复（固件级 + OctoPrint） ----------
    def execute_printer_pause(self) -> bool:
        try:
            ok_fw = self._firmware_pause()
            if not ok_fw:
                self.logger.warning("[PAUSE] firmware pause failed (continue to /api/job)")
            r = self._post("/api/job", {"command": "pause", "action": "pause"})
            if r.status_code not in (204, 200):
                self.logger.warning(f"[PAUSE] OctoPrint returned {r.status_code}: {r.text}")
            self._cached_state = PrinterState.PAUSED
            self.logger.info("[PAUSE] Done (firmware + job).")
            return True
        except Exception as e:
            self.logger.error(f"[PAUSE] failed: {e}")
            return False

    def execute_printer_resume(self) -> bool:
        try:
            ok_fw = self._firmware_resume()
            if not ok_fw:
                self.logger.warning("[RESUME] firmware resume failed (continue to /api/job)")
            r = self._post("/api/job", {"command": "pause", "action": "resume"})
            if r.status_code not in (204, 200):
                self.logger.warning(f"[RESUME] OctoPrint returned {r.status_code}: {r.text}")
            self._cached_state = PrinterState.PRINTING
            self.logger.info("[RESUME] Done (firmware + job).")
            return True
        except Exception as e:
            self.logger.error(f"[RESUME] failed: {e}")
            return False

    # ---- 兼容：旧方法名 pause()/resume() ----
    def pause(self) -> bool:
        return self.execute_printer_pause()

    def resume(self) -> bool:
        return self.execute_printer_resume()

    # ---------- 热床到温 ----------
    def is_bed_heat_complete(self) -> bool:
        """
        /api/printer 查询热床温度：
        - target==0 视为完成
        - |actual-target| <= bed_tolerance_c 视为完成
        - 出错保守返回 True（不阻塞）
        """
        try:
            r = self._get("/api/printer")
            if r.status_code != 200:
                self.logger.warning(f"[BED] /api/printer -> {r.status_code}")
                return True
            data = r.json()
            bed = (data.get("temperature", {}) or {}).get("bed", {}) or {}
            actual = bed.get("actual", 0.0) or 0.0
            target = bed.get("target", 0.0) or 0.0
            if target <= 0.0:
                return True
            return abs(actual - target) <= self.bed_tol
        except Exception as e:
            self.logger.error(f"[BED] is_bed_heat_complete failed: {e}")
            return True

    # ---------- 喷嘴到温 ----------
    def is_hotend_heat_complete(self, tol_c: float = 3.0) -> bool:
        """
        检查主喷嘴（tool0）是否到温：
        - target==0 视为完成
        - |actual-target| <= tol_c 视为完成
        - 出错保守返回 True（不阻塞）
        """
        try:
            r = self._get("/api/printer")
            if r.status_code != 200:
                self.logger.warning(f"[NOZZLE] /api/printer -> {r.status_code}")
                return True
            data = r.json()
            tool = (data.get("temperature", {}) or {}).get("tool0", {}) or {}
            actual = tool.get("actual", 0.0) or 0.0
            target = tool.get("target", 0.0) or 0.0
            if target <= 0.0:
                return True
            return abs(actual - target) <= tol_c
        except Exception as e:
            self.logger.error(f"[NOZZLE] is_hotend_heat_complete failed: {e}")
            return True

    # ---------- 进度 ----------
    def get_progress(self) -> Dict[str, Any]:
        """
        返回统一且向后兼容的进度信息，保证以下键永远存在：
        - progress_percent / completion
        - state / state_str
        - file / file_name
        - printTime / print_time
        - printTimeLeft / print_time_left
        - bed_heat_complete / nozzle_heat_complete
        - bed_actual / bed_target / nozzle_actual / nozzle_target
        """
        info = {
            "progress_percent": 0.0,
            "completion": 0.0,
            "state": self.state.name,   # 会刷新
            "state_str": self.state.name,
            "file": None,
            "file_name": None,
            "printTime": None,
            "print_time": None,
            "printTimeLeft": None,
            "print_time_left": None,
            "bed_heat_complete": True,
            "nozzle_heat_complete": True,
            "bed_actual": None,
            "bed_target": None,
            "nozzle_actual": None,
            "nozzle_target": None,
        }

        # 1) /api/job: 进度、文件、状态
        try:
            r = self._get("/api/job")
            if r.status_code == 200:
                j = r.json()
                # 进度
                p = (j.get("progress") or {})
                comp = p.get("completion", None)
                if comp is not None:
                    info["progress_percent"] = float(comp)
                    info["completion"] = float(comp)
                info["printTime"] = p.get("printTime", None)
                info["print_time"] = info["printTime"]
                info["printTimeLeft"] = p.get("printTimeLeft", None)
                info["print_time_left"] = info["printTimeLeft"]
                # 文件
                f = (j.get("job") or {}).get("file") or {}
                info["file"] = f.get("display") or f.get("name")
                info["file_name"] = info["file"]
                # 状态
                st = str(j.get("state", "")).upper()
                if st:
                    info["state"] = st
                    info["state_str"] = st
        except Exception as e:
            self.logger.error(f"[PROGRESS] /api/job failed: {e}")

        # 2) /api/printer: 温度与加热完成判定
        try:
            r2 = self._get("/api/printer")
            if r2.status_code == 200:
                data = r2.json()
                temp = data.get("temperature", {}) or {}
                bed = temp.get("bed", {}) or {}
                tool = temp.get("tool0", {}) or {}

                bed_actual = bed.get("actual", None)
                bed_target = bed.get("target", None)
                noz_actual = tool.get("actual", None)
                noz_target = tool.get("target", None)

                info["bed_actual"] = bed_actual
                info["bed_target"] = bed_target
                info["nozzle_actual"] = noz_actual
                info["nozzle_target"] = noz_target

                # 完成判定（与独立方法保持一致）
                info["bed_heat_complete"] = self.is_bed_heat_complete()
                info["nozzle_heat_complete"] = self.is_hotend_heat_complete()
        except Exception as e:
            self.logger.error(f"[PROGRESS] /api/printer failed: {e}")

        # 兜底
        if info["progress_percent"] is None:
            info["progress_percent"] = 0.0
        if info["completion"] is None:
            info["completion"] = 0.0

        return info


# -------------------- 简易自测 --------------------
if __name__ == "__main__":
    URL = os.environ.get("OCTO_URL", "http://octopi.local")
    KEY = os.environ.get("OCTO_KEY", "REPLACE_ME")
    MODE = os.environ.get("FW_MODE", "prusa")  # prusa / marlin_quickstop / marlin_sd / none

    s = GCodeSender(URL, KEY, firmware_mode=MODE)
    print("[TEST] State:", s.state.name)
    # print(s.get_progress())
    # s.pause(); time.sleep(1); s.resume()
    # s.start_print("/path/to/file.gcode")