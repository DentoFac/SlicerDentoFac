# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2024, Gauthier DOT
# Adapted by DentoFac from SlicerDentalSegmentator commit 476043f00009c372f0653dc759d69e2e559ed0f4; modified from upstream.

import json
import platform
import datetime
from typing import Dict, Any, List, Optional, Callable

from DentoFacLib.Diagnostics import DiagnosticsCollector


EXTENSION_NAME = "SlicerDentoFac"

def tail_logs(logs: List[str], max_lines: int = 100, max_bytes: int = 16384) -> List[str]:
    """Return the tail of a log list, bounded by lines and roughly by characters."""
    if not logs:
        return []
    
    tailed = logs[-max_lines:]
    # Calculate byte size approximately as string length
    total_len = sum(len(line) for line in tailed)
    while total_len > max_bytes and len(tailed) > 1:
        total_len -= len(tailed[0])
        tailed.pop(0)
    return tailed

def _get_torch_info() -> Dict[str, Any]:
    info = {
        "installed": False,
        "version": None,
        "cuda_version": None,
        "cuda_available": False,
        "gpu_name": None,
        "cuda_status": None,
    }
    try:
        import torch
        info["installed"] = True
        info["version"] = getattr(torch, "__version__", "unknown")
        info["cuda_version"] = getattr(torch.version, "cuda", None)
        info["cuda_available"] = torch.cuda.is_available()
        if info["cuda_available"]:
            try:
                info["gpu_name"] = torch.cuda.get_device_name(0)
            except Exception:
                pass
    except ImportError:
        pass
    except Exception:
        pass

    try:
        from .InstallationStatus import cuda_diagnostic
        info["cuda_status"] = cuda_diagnostic()
    except Exception:
        pass

    return info

class SupportDiagnostics:
    """
    Collects and serializes support diagnostics data.
    
    JSON Schema:
    {
        "timestamp": "ISO 8601 string",
        "platform": "OS platform string",
        "slicer_version": "Slicer version string or null",
        "module_version": "Extension version string or null",
        "extension_paths": {
            "module_root": "Path string or null",
            "model_root": "Path string or null"
        },
        "nnunet_available": true/false,
        "torch": {
            "installed": true/false,
            "version": "string or null",
            "cuda_version": "string or null",
            "cuda_available": true/false,
            "gpu_name": "string or null"
        },
        "compute_device": {
            "selected": "string or null",
            "actual": "string or null"
        },
        "model_validation": {
            "status": "string (e.g. VALID, MISSING)",
            "authoritative": true/false,
            "reason": "string or null",
            "config_folder": "Path string or null"
        },
        "logs": ["line1", "line2", ...]
    }
    """

    def __init__(
        self,
        get_slicer_version: Callable[[], Optional[str]] = None,
        get_module_version: Callable[[], Optional[str]] = None,
        get_module_root: Callable[[], Optional[str]] = None,
        get_model_root: Callable[[], Optional[str]] = None,
        is_nnunet_installed: Callable[[], bool] = None,
        get_torch_info_f: Callable[[], Dict[str, Any]] = None,
        get_status_f: Callable[[str], Any] = None,
        get_logs_f: Callable[[], List[str]] = None,
        device_text: str = "cuda"
    ):
        self._get_slicer_version = get_slicer_version or self._default_get_slicer_version
        self._get_module_version = get_module_version or self._default_get_module_version
        self._get_module_root = get_module_root or self._default_get_module_root
        self._get_model_root = get_model_root or self._default_get_model_root
        self._is_nnunet_installed = is_nnunet_installed or self._default_is_nnunet_installed
        self._get_torch_info = get_torch_info_f or _get_torch_info
        self._get_status = get_status_f or self._default_get_status
        self._get_logs = get_logs_f or self._default_get_logs
        self.device_text = device_text

    def _default_get_slicer_version(self) -> Optional[str]:
        try:
            import slicer
            return slicer.app.applicationVersion
        except ImportError:
            return None
        except Exception:
            return None

    def _default_get_module_version(self) -> Optional[str]:
        try:
            import slicer
            if hasattr(slicer.app, "extensionsManagerModel"):
                model = slicer.app.extensionsManagerModel()
                if model:
                    return model.extensionVersion(EXTENSION_NAME)
        except Exception:
            pass
        return None

    def _default_get_module_root(self) -> Optional[str]:
        try:
            from pathlib import Path
            import DentoFacSegmentatorLib
            return str(Path(DentoFacSegmentatorLib.__file__).parent.parent)
        except Exception:
            return None

    def _default_get_model_root(self) -> Optional[str]:
        try:
            from .ModelPath import modelRoot
            return str(modelRoot())
        except Exception:
            return None

    def _default_is_nnunet_installed(self) -> bool:
        try:
            from .SegmentationWidget import SegmentationWidget
            return SegmentationWidget.isNNUNetModuleInstalled()
        except Exception:
            return False

    def _default_get_status(self, device_text: str):
        try:
            from .InstallationStatus import collect_status
            return collect_status(device_text, check_online=False)
        except Exception:
            return None

    def _default_get_logs(self) -> List[str]:
        return []

    def collect(self) -> Dict[str, Any]:
        shared_runtime = DiagnosticsCollector().collect()
        data = {
            "timestamp": shared_runtime["timestamp"],
            "platform": shared_runtime["platform"],
            "shared_runtime": shared_runtime,
            "slicer_version": None,
            "module_version": None,
            "extension_paths": {
                "module_root": None,
                "model_root": None
            },
            "nnunet_available": False,
            "torch": {
                "installed": False,
                "version": None,
                "cuda_version": None,
                "cuda_available": False,
                "gpu_name": None
            },
            "compute_device": {
                "selected": self.device_text,
                "actual": None
            },
            "model_validation": {
                "status": "UNAVAILABLE",
                "authoritative": False,
                "reason": None,
                "config_folder": None
            },
            "logs": []
        }

        try:
            data["slicer_version"] = self._get_slicer_version()
        except Exception:
            pass

        try:
            data["module_version"] = self._get_module_version()
        except Exception:
            pass

        try:
            data["extension_paths"]["module_root"] = self._get_module_root()
        except Exception:
            pass

        try:
            data["extension_paths"]["model_root"] = self._get_model_root()
        except Exception:
            pass

        try:
            data["nnunet_available"] = self._is_nnunet_installed()
        except Exception:
            pass

        try:
            data["torch"] = self._get_torch_info()
        except Exception:
            pass

        try:
            status = self._get_status(self.device_text)
            if status:
                data["compute_device"]["actual"] = getattr(status, "actual_device", None)

                if hasattr(status, "val_res"):
                    res = status.val_res
                    data["model_validation"]["status"] = res.status.name if hasattr(res.status, "name") else str(res.status)
                    data["model_validation"]["authoritative"] = res.authoritative
                    data["model_validation"]["reason"] = res.reason
                    data["model_validation"]["config_folder"] = str(res.configurationFolder) if res.configurationFolder else None
        except Exception:
            pass

        try:
            raw_logs = self._get_logs()
            data["logs"] = tail_logs(raw_logs)
        except Exception:
            pass

        return data

    def serialize_json(self, data: Dict[str, Any]) -> str:
        return json.dumps(data, indent=2)

    def serialize_markdown(self, data: Dict[str, Any]) -> str:
        def _get(d, key, default="Unknown"):
            val = d.get(key)
            return default if val is None else val

        lines = []
        lines.append("## Support Diagnostics")
        lines.append("")
        
        lines.append("### Environment")
        lines.append(f"- **Timestamp:** {_get(data, 'timestamp')}")
        lines.append(f"- **Platform:** {_get(data, 'platform')}")
        lines.append(f"- **Slicer Version:** {_get(data, 'slicer_version')}")
        lines.append(f"- **Module Version:** {_get(data, 'module_version')}")
        
        paths = data.get("extension_paths", {})
        lines.append(f"- **Module Root:** {_get(paths, 'module_root')}")
        lines.append(f"- **Model Root:** {_get(paths, 'model_root')}")
        lines.append("")
        
        lines.append("### Dependencies")
        lines.append(f"- **NNUNet Available:** {_get(data, 'nnunet_available', False)}")
        
        torch_info = data.get("torch", {})
        lines.append(f"- **PyTorch Installed:** {_get(torch_info, 'installed', False)}")
        if torch_info.get("installed"):
            lines.append(f"- **PyTorch Version:** {_get(torch_info, 'version')}")
            lines.append(f"- **CUDA Version (compiled):** {_get(torch_info, 'cuda_version', 'None')}")
            lines.append(f"- **CUDA Available (runtime):** {_get(torch_info, 'cuda_available', False)}")
            if torch_info.get("gpu_name"):
                lines.append(f"- **GPU Name:** {torch_info.get('gpu_name')}")
            if torch_info.get("cuda_status"):
                lines.append(f"- **CUDA Status:** {torch_info.get('cuda_status')}")
        lines.append("")
        
        lines.append("### Status")
        comp_dev = data.get("compute_device", {})
        lines.append(f"- **Selected Device:** {_get(comp_dev, 'selected')}")
        lines.append(f"- **Actual Device:** {_get(comp_dev, 'actual')}")
        
        mod_val = data.get("model_validation", {})
        lines.append(f"- **Model Status:** {_get(mod_val, 'status')}")
        lines.append(f"- **Authoritative:** {_get(mod_val, 'authoritative', False)}")
        if mod_val.get("reason"):
            lines.append(f"- **Reason:** {mod_val.get('reason')}")
        if mod_val.get("config_folder"):
            lines.append(f"- **Config Folder:** {mod_val.get('config_folder')}")
        lines.append("")
        
        lines.append("### Logs")
        logs = data.get("logs", [])
        if logs:
            lines.append("```")
            for line in logs:
                lines.append(line)
            lines.append("```")
        else:
            lines.append("*No logs available.*")
        
        return "\n".join(lines)

    def prepare_github_issue_body(self, md_text: str, max_len: int = 7000) -> str:
        """Returns the markdown body for a GitHub issue, truncating logs if it exceeds max_len."""
        import urllib.parse
        if len(urllib.parse.quote(md_text)) <= max_len:
            return md_text
            
        if "\n### Logs" in md_text:
            idx = md_text.find("\n### Logs")
            fallback = "<!-- Please attach the saved JSON file below -->\n\n" + md_text[:idx] + "\n### Logs\n<Logs truncated due to length - please attach saved JSON file>\n"
            return fallback
            
        return md_text
