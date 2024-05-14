#!/usr/bin/env python3
# -*- coding: utf8 -*-
# MIT License
#
# Copyright (c) 2023-2024 Ravener
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

import sys
from argparse import ArgumentParser
from dataclasses import dataclass
from pathlib import Path

CARD_SIZE = 128 * 1024  # 128 KiB raw memory card file size.
BLOCK_SIZE = 8 * 1024  # 8 KiB per block (16 blocks total)
FRAME_SIZE = 128  # 128 bytes per frame (64 frames total)

# 00h-03h Block Allocation State
# 00000051h - In use ;first-or-only block of a file
# 00000052h - In use ;middle block of a file (if 3 or more blocks)
# 00000053h - In use ;last block of a file   (if 2 or more blocks)
# 000000A0h - Free   ;freshly formatted
# 000000A1h - Free   ;deleted (first-or-only block of file)
# 000000A2h - Free   ;deleted (middle block of file)
# 000000A3h - Free   ;deleted (last block of file)
FIRST = 0x51


# A container to store directory information.
@dataclass
class DirectoryFrame:
    state: int
    file_size: int = 0
    pointer: int = 0
    file_name: str = None


def read_block(data: bytes, i: int):
    """Returns the subarray of data including only the requested block."""
    return data[i * BLOCK_SIZE : i * BLOCK_SIZE + BLOCK_SIZE]


def parse_header(data: bytes) -> list[DirectoryFrame]:
    directories = []

    # Explanation of the range:
    # • Start at FRAME_SIZE (skipping the header frame)
    # • Go until we reach 16 frames
    # • Jump FRAME_SIZE steps so each iteration is a frame.
    for i in range(FRAME_SIZE, 16 * FRAME_SIZE, FRAME_SIZE):
        frame = DirectoryFrame(int.from_bytes(data[i : i + 4], "little"))

        # The following information is only available in the first blocks.
        if frame.state == FIRST:
            frame.file_size = int.from_bytes(data[i + 4 : i + 7], "little")
            frame.pointer = data[i + 8]
            frame.file_name = data[i + 10 : i + 31].decode("shift_jis").strip("\x00")

        directories.append(frame)

    return directories


def verify_file(data: bytes) -> bool:
    """
    Verifies that the given data is a valid card.

    Checks that the card size is 128 KB and starts with the magic MC
    """
    if len(data) != CARD_SIZE:
        return False

    if data[:2] != b"MC":
        return False

    return True


def get_title(data: bytes, i: int) -> str:
    block = read_block(data, i + 1)
    return block[4:68].decode("shift_jis").strip("\x00")


def main() -> None:
    parser = ArgumentParser()
    parser.add_argument("input", help="The raw memory card file.")
    args = parser.parse_args()
    data = Path(args.input).read_bytes()

    if not verify_file(data):
        print("The given file is not a memory card.")
        sys.exit(1)

    directories = parse_header(read_block(data, 0))
    print("File Name            | Size   | Blocks    | Title")
    total_size = 0

    for i, directory in enumerate(directories):
        if directory.state == FIRST:
            name = directory.file_name.ljust(20)
            size = f"{str(directory.file_size // 1024).center(3)} KB"
            blocks = f"{str(directory.file_size // BLOCK_SIZE).center(2)} Block"

            # Make the word plural
            if directory.file_size > 8192:
                blocks += "s"
            else:
                # Add a space anyway for padding.
                blocks += " "

            title = get_title(data, i)
            total_size += directory.file_size
            print(f"{name} | {size} | {blocks} | {title}")

    print()
    print(f"• Total Size: {total_size // 1024} KB ({total_size // 8192} Blocks)")
    # We consider the free space from 120 KB because the first block
    # is always the header block and so nothing can be stored there.
    print(
        f"• Free Space: {120 - total_size // 1024} KB ({15 - total_size // 8192} Blocks)"
    )
    print()
    print("Filename prefix: BI = Japan, BE = Europe, BA = America")


if __name__ == "__main__":
    main()
