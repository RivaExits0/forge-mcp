"""Game profile / adapter loader."""

from __future__ import annotations

import json
import os
import tomllib
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class GameProfile:
    name: str
    path: str
    data: Dict[str, Any] = field(default_factory=dict)
    signatures: Dict[str, Any] = field(default_factory=dict)
    schema_path: Optional[str] = None

    @property
    def adapter_dir(self) -> str:
        return self.path

    def get(self, key: str, default=None):
        return self.data.get(key, default)


def load_profile(profile_dir: str) -> GameProfile:
    if not os.path.isdir(profile_dir):
        raise FileNotFoundError(profile_dir)
    toml_path = os.path.join(profile_dir, "profile.toml")
    data: Dict[str, Any] = {}
    if os.path.isfile(toml_path):
        with open(toml_path, "rb") as f:
            data = tomllib.load(f)
    name = data.get("name") or os.path.basename(os.path.rstrip(profile_dir, "/"))
    sig_path = os.path.join(profile_dir, "signatures.json")
    signatures = {}
    if os.path.isfile(sig_path):
        with open(sig_path, encoding="utf-8") as f:
            signatures = json.load(f)
    schema_path = None
    for cand in ("schema.ksy", "schema.hexpat"):
        p = os.path.join(profile_dir, cand)
        if os.path.isfile(p):
            schema_path = p
            break
    return GameProfile(name=name, path=profile_dir, data=data, signatures=signatures,
                       schema_path=schema_path)


def list_profiles(profiles_root: str) -> List[str]:
    if not os.path.isdir(profiles_root):
        return []
    out = []
    for n in sorted(os.listdir(profiles_root)):
        d = os.path.join(profiles_root, n)
        if os.path.isdir(d) and (os.path.isfile(os.path.join(d, "profile.toml"))
                                 or os.path.isfile(os.path.join(d, "signatures.json"))):
            out.append(n)
    return out