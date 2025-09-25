#!/usr/bin/env python3
"""
Simple Log Viewer for Amanuensis
Displays recent log entries with filtering and color coding
"""

import os
import glob
import sys
import re
from datetime import datetime, timedelta
import argparse


class LogViewer:
    """Simple log viewer with filtering capabilities"""

    def __init__(self):
        self.colors = {
            'DEBUG': '\033[36m',    # Cyan
            'INFO': '\033[32m',     # Green
            'WARNING': '\033[33m',  # Yellow
            'ERROR': '\033[31m',    # Red
            'RESET': '\033[0m',     # Reset
            'BOLD': '\033[1m',      # Bold
        }

    def get_latest_logs(self, log_type='main'):
        """Get the latest log files"""
        log_dir = "logs"
        if not os.path.exists(log_dir):
            print(f"Log directory '{log_dir}' not found!")
            return []

        if log_type == 'main':
            pattern = "amanuensis_*.log"
        elif log_type == 'audio':
            pattern = "amanuensis_audio_*.log"
        elif log_type == 'errors':
            pattern = "amanuensis_errors_*.log"
        else:
            pattern = "*.log"

        log_files = glob.glob(os.path.join(log_dir, pattern))

        # Sort by modification time (newest first)
        log_files.sort(key=os.path.getmtime, reverse=True)

        return log_files

    def colorize_log_level(self, line):
        """Add color to log levels"""
        if not sys.stdout.isatty():
            return line  # No color if not terminal

        for level in ['DEBUG', 'INFO', 'WARNING', 'ERROR']:
            if f'| {level} ' in line:
                return line.replace(f'| {level} ', f'| {self.colors[level]}{level}{self.colors["RESET"]} ')

        return line

    def filter_logs(self, lines, level=None, component=None, search=None, last_minutes=None):
        """Filter log lines based on criteria"""
        filtered = []

        # Calculate time cutoff if specified
        cutoff_time = None
        if last_minutes:
            cutoff_time = datetime.now() - timedelta(minutes=last_minutes)

        for line in lines:
            # Time filtering
            if cutoff_time:
                try:
                    # Extract timestamp from log line
                    timestamp_match = re.match(r'^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})', line)
                    if timestamp_match:
                        log_time = datetime.strptime(timestamp_match.group(1), '%Y-%m-%d %H:%M:%S')
                        if log_time < cutoff_time:
                            continue
                except ValueError:
                    pass  # Skip lines without valid timestamps

            # Level filtering
            if level and f'| {level.upper()} ' not in line:
                continue

            # Component filtering
            if component and f'| {component} ' not in line:
                continue

            # Search filtering
            if search and search.lower() not in line.lower():
                continue

            filtered.append(line)

        return filtered

    def view_logs(self, log_type='main', lines=50, level=None, component=None,
                  search=None, last_minutes=None, follow=False):
        """View log files with filtering"""

        log_files = self.get_latest_logs(log_type)
        if not log_files:
            print(f"No {log_type} log files found!")
            return

        latest_log = log_files[0]
        print(f"{self.colors['BOLD']}Viewing: {latest_log}{self.colors['RESET']}")
        print("=" * 80)

        try:
            with open(latest_log, 'r', encoding='utf-8') as f:
                all_lines = f.readlines()

            # Apply filters
            filtered_lines = self.filter_logs(
                all_lines, level, component, search, last_minutes
            )

            # Show last N lines
            display_lines = filtered_lines[-lines:] if lines else filtered_lines

            for line in display_lines:
                colored_line = self.colorize_log_level(line.rstrip())
                print(colored_line)

            print("=" * 80)
            print(f"Showing {len(display_lines)} of {len(filtered_lines)} filtered lines "
                  f"(total: {len(all_lines)} lines)")

        except Exception as e:
            print(f"Error reading log file: {e}")

    def list_components(self, log_type='main'):
        """List available components in logs"""
        log_files = self.get_latest_logs(log_type)
        if not log_files:
            return

        components = set()
        try:
            with open(log_files[0], 'r', encoding='utf-8') as f:
                for line in f:
                    # Extract component name from log format
                    match = re.search(r'\| ([^|]+) +\| \w+ +\|', line)
                    if match:
                        components.add(match.group(1).strip())

            print("Available components:")
            for comp in sorted(components):
                print(f"  - {comp}")

        except Exception as e:
            print(f"Error reading log file: {e}")


def main():
    parser = argparse.ArgumentParser(description="View Amanuensis logs")
    parser.add_argument('--type', choices=['main', 'audio', 'errors', 'all'],
                       default='main', help='Log type to view')
    parser.add_argument('--lines', '-n', type=int, default=50,
                       help='Number of lines to show (0 for all)')
    parser.add_argument('--level', choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
                       help='Filter by log level')
    parser.add_argument('--component', help='Filter by component name')
    parser.add_argument('--search', help='Search for text in log lines')
    parser.add_argument('--last', type=int, help='Show only logs from last N minutes')
    parser.add_argument('--list-components', action='store_true',
                       help='List available components')

    args = parser.parse_args()

    viewer = LogViewer()

    if args.list_components:
        viewer.list_components(args.type)
        return

    viewer.view_logs(
        log_type=args.type,
        lines=args.lines,
        level=args.level,
        component=args.component,
        search=args.search,
        last_minutes=args.last
    )


if __name__ == "__main__":
    main()