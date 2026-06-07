#!/usr/bin/env python3
"""
Test Google Drive access using the app's connector (service account → shared folders).

Run via dev toolbox (no host pip install):
  ./dev/tools.sh drive-test
  ./dev/tools.sh drive-test --folder-id <id>   # optional scope to one folder
  ./dev/tools.sh drive-test --pdf-only
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

# Import from the PdfDing app package
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "pdfding"))

from pdf.drive.google_drive_connector import (  # noqa: E402
    DriveConnectionError,
    DriveTreeNode,
    GoogleDriveConnector,
    count_tree_items,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Test Drive service account → shared folders")
    parser.add_argument(
        "--key-file",
        default=os.environ.get("GOOGLE_DRIVE_KEY_FILE"),
        help="Path to service account JSON (or GOOGLE_DRIVE_KEY_FILE)",
    )
    parser.add_argument(
        "--folder-id",
        default=os.environ.get("GOOGLE_DRIVE_FOLDER_ID") or None,
        help="Optional: scope to one folder ID (or GOOGLE_DRIVE_FOLDER_ID)",
    )
    parser.add_argument("--pdf-only", action="store_true", help="Only include PDF files in the tree")
    return parser.parse_args()


def print_tree(nodes: list[DriveTreeNode], indent: int = 0) -> None:
    prefix = "  " * indent
    for node in nodes:
        kind = "DIR " if node.is_folder else "FILE"
        print(f"{prefix}{kind}  {node.name}")
        if node.children:
            print_tree(node.children, indent + 1)


def filter_pdf_nodes(nodes: list[DriveTreeNode]) -> list[DriveTreeNode]:
    filtered: list[DriveTreeNode] = []
    for node in nodes:
        if node.is_folder:
            children = filter_pdf_nodes(node.children)
            if children:
                filtered.append(
                    DriveTreeNode(
                        id=node.id,
                        name=node.name,
                        mime_type=node.mime_type,
                        is_folder=True,
                        children=children,
                    )
                )
        elif node.mime_type == "application/pdf":
            filtered.append(node)
    return filtered


def main() -> int:
    args = parse_args()

    if not args.key_file:
        print("ERROR: Provide --key-file or set GOOGLE_DRIVE_KEY_FILE", file=sys.stderr)
        return 1

    key_file = Path(args.key_file).expanduser().resolve()
    if not key_file.is_file():
        print(f"ERROR: Key file not found: {key_file}", file=sys.stderr)
        return 1

    print("=== Google Drive connection test ===\n")
    print(f"Key file:   {key_file}")
    if args.folder_id:
        print(f"Scope:      folder {args.folder_id}")
    else:
        print("Scope:      all folders/files shared with the service account")
    print()

    connector = GoogleDriveConnector(key_file)
    print(f"Service account: {connector.service_account_email}\n")

    try:
        tree = connector.list_shared_hierarchy(root_folder_id=args.folder_id)
    except DriveConnectionError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    if args.pdf_only:
        tree = filter_pdf_nodes(tree)

    if not tree:
        print("No shared folders or files found.")
        return 0

    print("Shared hierarchy:\n")
    print_tree(tree)

    folder_count, file_count = count_tree_items(tree)
    print(f"\nTotal: {folder_count} folder(s), {file_count} file(s)")
    print("\nConnection test passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
