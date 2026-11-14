# Forge-Mcp Demo

> **Demo recording placeholder** — Replace this with a GIF or video recording of the example workflow.

## Recording Script

See [demo-script.md](demo-script.md) for the exact sequence of MCP tool calls to record.

## Expected Output

The demo should show:

1. **Open Game** — Create workspace, import `example.exe`
2. **Value Scan** — Compare `save_100.bin` vs `save_150.bin` to find gold offset
3. **Hex View** — Inspect bytes around the found offset
4. **Make Signature** — Generate AOB signature at that offset
5. **Verify Signature** — Confirm signature uniquely matches in updated binary
6. **Export Patch** — Create IPS patch file
6. **Undo** — Demonstrate snapshot rollback

---

*To record: Use a terminal recorder like `asciinema`, `vhs`, or OBS. Run the MCP server and send tool calls via Claude Desktop or an MCP test client.*