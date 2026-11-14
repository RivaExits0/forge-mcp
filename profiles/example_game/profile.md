# Elden Ring Game Profile Example

This is a sample game profile (adapter) for Elden Ring.
Copy this folder to `profiles/elden_ring/` and load with:
```python
open_game({"game_name": "elden_ring", "profile_dir": "profiles/elden_ring"})
```

## profile.toml
```toml
name = "elden_ring"
version = "1.0"
author = "forge-mcp community"
description = "Elden Ring save/table offsets and signatures"

[files]
save = "save.bin"
exe = "eldenring.exe"

[offsets]
gold = 0x3A20
runes = 0x3A24
level = 0x3A28

[tables]
items = "item_table.bin"
```

## signatures.json
```json
{
  "gold_value": "8B 45 ?? 3D 96 00 00 00 75 ?? 48 8B 0D",
  "runes_function": "48 89 5C 24 ?? 48 89 74 24 ?? 57 48 83 EC 20 48 8B F9 8B 59",
  "item_get": "40 53 48 83 EC 20 48 8B D9 48 8B 0D ?? ?? ?? ?? 48 85 C9"
}
```

## schema.ksy (Kaitai Struct for item table)
```yaml
meta:
  id: elden_ring_item_table
  endian: le
seq:
  - id: count
    type: u4
  - id: offsets
    type: u4
    repeat: expr
    repeat-expr: count
  - id: entries
    type: item_entry
    repeat: expr
    repeat-expr: count
types:
  item_entry:
    seq:
      - id: id
        type: u4
      - id: quantity
        type: u4
      - id: flags
        type: u4
      - id: name_offset
        type: u4
    instances:
      name:
        pos: name_offset
        type: strz
        encoding: utf-8
```