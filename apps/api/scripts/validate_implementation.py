"""
Validation Script for Memory Recall v4.0.0

Run this script to validate the implementation:
    python scripts/validate_implementation.py
"""

import asyncio
import sys
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))

PASS = "✅"
FAIL = "❌"
SKIP = "⏭️"


class ValidationResult:
    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.skipped = 0
        self.results = []

    def add(self, name: str, status: str, message: str = ""):
        self.results.append((name, status, message))
        if status == PASS:
            self.passed += 1
        elif status == FAIL:
            self.failed += 1
        else:
            self.skipped += 1

    def print_report(self):
        print("\n" + "=" * 60)
        print("VALIDATION REPORT")
        print("=" * 60)

        for name, status, message in self.results:
            print(f"{status} {name}")
            if message:
                print(f"   {message}")

        print("\n" + "-" * 60)
        print(
            f"Passed: {self.passed} | Failed: {self.failed} | Skipped: {self.skipped}"
        )
        print("-" * 60 + "\n")

        return self.failed == 0


def check_file_exists(path: str) -> bool:
    return Path(path).exists()


def check_directory_exists(path: str) -> bool:
    return Path(path).is_dir()


def validate_phase_1_3(result: ValidationResult):
    """Validate: Database Schema Clean"""
    print("\n[Phase 1-3] Database Schema Clean...")

    if check_file_exists("migrations/017_clean_and_evolve.sql"):
        result.add("Migration 017 exists", PASS)
    else:
        result.add("Migration 017 exists", FAIL, "File not found")

    if not check_directory_exists("src/openclaw_plugin"):
        result.add("openclaw_plugin deleted", PASS)
    else:
        result.add("openclaw_plugin deleted", FAIL, "Directory still exists")

    if not check_file_exists("src/services/memory_service.py"):
        result.add("Legacy memory_service.py deleted", PASS)
    else:
        result.add("Legacy memory_service.py deleted", FAIL, "File still exists")


def validate_phase_4_6(result: ValidationResult):
    """Validate: Schema Evolution"""
    print("\n[Phase 4-6] Schema Evolution...")

    migration_content = ""
    migration_path = Path("migrations/017_clean_and_evolve.sql")
    if migration_path.exists():
        migration_content = migration_path.read_text()

    tables = [
        "api_keys",
        "memory_relations",
        "user_profiles",
        "facts",
        "notifications",
        "content_chunks",
    ]
    for table in tables:
        if f"CREATE TABLE IF NOT EXISTS {table}" in migration_content:
            result.add(f"Table {table} defined", PASS)
        else:
            result.add(f"Table {table} defined", FAIL, "Not found in migration")

    columns = [
        "event_date",
        "expiration_date",
        "memory_lifespan",
        "memory_behavior",
        "chunk_count",
    ]
    for col in columns:
        if col in migration_content:
            result.add(f"Column {col} defined", PASS)
        else:
            result.add(f"Column {col} defined", FAIL, "Not found in migration")


def validate_phase_7_8(result: ValidationResult):
    """Validate: Core Refactor + Auth"""
    print("\n[Phase 7-8] Core Refactor + Auth...")

    if check_directory_exists("src/services/core"):
        result.add("services/core/ directory exists", PASS)
    else:
        result.add("services/core/ directory exists", FAIL)

    if check_file_exists("src/services/core/memory_service.py"):
        result.add("memory_service.py renamed", PASS)
    else:
        result.add("memory_service.py renamed", FAIL)

    if check_file_exists("src/api/auth.py"):
        result.add("auth.py exists", PASS)
    else:
        result.add("auth.py exists", FAIL)


def validate_phase_9(result: ValidationResult):
    """Validate: API v1"""
    print("\n[Phase 9] API v1 Endpoints...")

    endpoints = [
        "src/api/v1/auth.py",
        "src/api/v1/memories.py",
        "src/api/v1/recall.py",
        "src/api/v1/containers.py",
        "src/api/v1/relations.py",
        "src/api/v1/profile.py",
        "src/api/v1/notifications.py",
    ]

    for endpoint in endpoints:
        if check_file_exists(endpoint):
            result.add(f"{Path(endpoint).name} exists", PASS)
        else:
            result.add(f"{Path(endpoint).name} exists", FAIL)


def validate_phase_10_17(result: ValidationResult):
    """Validate: Evolution Services"""
    print("\n[Phase 10-17] Evolution Services...")

    services = [
        "src/services/evolution/user_profile_service.py",
        "src/services/evolution/temporal_service.py",
        "src/services/evolution/forgetting_service.py",
        "src/services/evolution/chunking_service.py",
        "src/services/evolution/fact_extraction_service.py",
        "src/services/evolution/importance_service.py",
        "src/services/evolution/fusion_service.py",
        "src/services/evolution/memory_behavior_service.py",
    ]

    for service in services:
        if check_file_exists(service):
            result.add(f"{Path(service).stem} exists", PASS)
        else:
            result.add(f"{Path(service).stem} exists", FAIL)


def validate_phase_18(result: ValidationResult):
    """Validate: Background Tasks"""
    print("\n[Phase 18] Background Tasks...")

    if check_file_exists("src/background/scheduler.py"):
        result.add("scheduler.py exists", PASS)
    else:
        result.add("scheduler.py exists", FAIL)


def validate_phase_23_25(result: ValidationResult):
    """Validate: Tests + Docs + Release"""
    print("\n[Phase 23-25] Tests + Docs + Release...")

    if check_file_exists("tests/test_v1/test_auth.py"):
        result.add("test_auth.py exists", PASS)
    else:
        result.add("test_auth.py exists", SKIP, "Optional")

    if check_file_exists("CHANGELOG.md"):
        result.add("CHANGELOG.md exists", PASS)
    else:
        result.add("CHANGELOG.md exists", FAIL)

    if check_file_exists("docs/DATABASE_SCHEMA.md"):
        result.add("DATABASE_SCHEMA.md exists", PASS)
    else:
        result.add("DATABASE_SCHEMA.md exists", FAIL)


async def main():
    print("=" * 60)
    print("MEMORY RECALL v4.0.0 - VALIDATION SCRIPT")
    print(f"Run Time: {datetime.now().isoformat()}")
    print("=" * 60)

    result = ValidationResult()

    validate_phase_1_3(result)
    validate_phase_4_6(result)
    validate_phase_7_8(result)
    validate_phase_9(result)
    validate_phase_10_17(result)
    validate_phase_18(result)
    validate_phase_23_25(result)

    success = result.print_report()

    if success:
        print("🎉 All validations passed!")
        return 0
    else:
        print("⚠️ Some validations failed. Please review.")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
