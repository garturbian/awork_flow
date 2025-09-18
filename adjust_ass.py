#!/usr/bin/env python3
"""
Extend subtitle durations in .ass files without overlaps, adding a safety buffer.
Usage: python adjust_ass.py input.ass output.ass 500
"""

import re
import sys
from datetime import timedelta, datetime

# Default safety buffer in milliseconds
BUFFER_MS = 50

def parse_time(timestr):
    # Format: h:mm:ss.cs  (e.g. 0:00:03.14)
    return datetime.strptime(timestr, "%H:%M:%S.%f")

def format_time(dt):
    return dt.strftime("%H:%M:%S.%f")[:-4]  # trim to 2 decimals

def adjust_ass_file(input_file, output_file, lead_out_ms, buffer_ms=BUFFER_MS):
    with open(input_file, "r", encoding="utf-8-sig") as f:
        lines = f.readlines()

    dialogue_lines = []
    pattern = re.compile(r"^(Dialogue: \d+),([\d:.]+),([\d:.]+),(.*)$")

    # Extract all dialogue lines
    for i, line in enumerate(lines):
        m = pattern.match(line)
        if m:
            start = parse_time(m.group(2))
            end = parse_time(m.group(3))
            dialogue_lines.append((i, start, end, m))

    # Adjust times
    for idx, (i, start, end, m) in enumerate(dialogue_lines):
        new_end = end + timedelta(milliseconds=lead_out_ms)

        # Prevent overlap with next subtitle and add safety buffer
        if idx + 1 < len(dialogue_lines):
            next_start = dialogue_lines[idx + 1][1]
            if new_end >= next_start - timedelta(milliseconds=buffer_ms):
                new_end = next_start - timedelta(milliseconds=buffer_ms)

        # Rebuild line
        new_line = f"{m.group(1)},{format_time(start)},{format_time(new_end)},{m.group(4)}\n"
        lines[i] = new_line

    # Write result
    with open(output_file, "w", encoding="utf-8") as f:
        f.writelines(lines)

    print(f"Adjusted file saved as {output_file} with lead-out {lead_out_ms} ms and buffer {buffer_ms} ms")

# Command-line interface
if __name__ == "__main__":
    if len(sys.argv) != 4:
        print("Usage: python adjust_ass.py input.ass output.ass lead_out_ms")
        sys.exit(1)

    input_file = sys.argv[1]
    output_file = sys.argv[2]
    lead_out_ms = int(sys.argv[3])

    adjust_ass_file(input_file, output_file, lead_out_ms)
