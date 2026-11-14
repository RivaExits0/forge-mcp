# Example Game Profile

This is a sample game profile (adapter) for a fictional game.
Copy this folder to `profiles/example_game/` and load with:

```python
open_game({"game_name": "example_game", "profile_dir": "profiles/example_game"})
```

## profile.toml
```toml
name = "example_game"
version = "1.0"
author = "forge-mcp"
description = "Example game save/table offsets and signatures"

[files]
save = "save.bin"
exe = "example.exe"

[offsets]
gold = 0x3A20
health = 0x3A24
level = 0x3A28

[tables]
items = "item_table.bin"
```

## signatures.json
```json
{
  "gold_value": "8B 45 ?? 3D 96 00 00 00 75 ?? 48 8B 0D",
  "health_function": "48 89 5C 24 ?? 48 89 74 24 ?? 57 48 83 EC 20 48 8B F9 8B 59",
  "item_get": "40 53 48 83 EC 20 48 8B D9 48 8B 0D ?? ?? ?? ?? 48 85 C9"
}
```

## schema.ksy (Kaitai Struct for item table)
```yaml
meta:
  id: example_game_item_table
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