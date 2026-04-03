"""
Validation Script for Memory Recall v5.1.5

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


def validate_database_schema(result: ValidationResult):
    """Validate: Database Schema"""
    print("\n[Database Schema] Checking schema.sql...")

    schema_content = ""
    schema_path = Path("schema.sql")
    if schema_path.exists():
        schema_content = schema_path.read_text()
        result.add("schema.sql exists", PASS)
    else:
        result.add("schema.sql exists", FAIL, "File not found")
        return

    # Check required tables
    tables = [
        ("api_keys", "API密钥管理"),
        ("memories", "核心记忆存储"),
        ("memory_relations", "记忆关系"),
        ("memory_profiles", "用户画像"),
        ("documents", "文档元数据"),
        ("chunks", "文档分块"),
        ("entities", "实体/知识图谱"),
        ("entity_relations", "实体关系"),
        ("memory_entities", "记忆-实体关联"),
    ]

    for table, desc in tables:
        if f"CREATE TABLE IF NOT EXISTS {table}" in schema_content:
            result.add(f"Table {table} ({desc})", PASS)
        else:
            result.add(f"Table {table} ({desc})", FAIL, "Not found in schema")

    # Check key fields
    key_fields = [
        ("memories.version", "版本控制"),
        ("memories.root_memory_id", "根记忆ID"),
        ("memories.is_inference", "推断标记"),
        ("memory_profiles.entity_context", "实体上下文"),
        ("api_keys.user_name", "用户名"),
        ("chunks.embedding", "分块嵌入"),
    ]

    for field, desc in key_fields:
        if field in schema_content:
            result.add(f"Field {field} ({desc})", PASS)
        else:
            result.add(f"Field {field} ({desc})", FAIL, "Not found in schema")


def validate_core_services(result: ValidationResult):
    """Validate: Core Services"""
    print("\n[Core Services] Checking service files...")

    services = [
        ("src/services/core/memory_store.py", "记忆存储"),
        ("src/services/core/relation_service.py", "关系服务"),
        ("src/services/core/profile_service.py", "画像服务"),
        ("src/services/core/document_store.py", "文档存储"),
        ("src/services/core/entity_extraction.py", "实体提取"),
        ("src/services/core/llm_entity_extraction.py", "LLM实体提取"),
    ]

    for service, desc in services:
        if check_file_exists(service):
            result.add(f"Service: {desc}", PASS)
        else:
            result.add(f"Service: {desc}", FAIL, f"Missing {service}")


def validate_api_endpoints(result: ValidationResult):
    """Validate: API Endpoints"""
    print("\n[API Endpoints] Checking endpoint files...")

    endpoints = [
        ("src/api/memories.py", "记忆接口"),
        ("src/api/auth.py", "认证接口"),
        ("src/api/graph.py", "图谱接口"),
        ("src/api/health.py", "健康检查"),
    ]

    for endpoint, desc in endpoints:
        if check_file_exists(endpoint):
            result.add(f"Endpoint: {desc}", PASS)
        else:
            result.add(f"Endpoint: {desc}", FAIL, f"Missing {endpoint}")


def validate_initialization(result: ValidationResult):
    """Validate: Initialization Files"""
    print("\n[Initialization] Checking init files...")

    if check_file_exists("init_db.py"):
        result.add("init_db.py exists", PASS)
    else:
        result.add("init_db.py exists", FAIL, "File not found")

    if check_file_exists("docker-entrypoint-initdb.d/schema.sql"):
        result.add("Docker init schema.sql", PASS)
    else:
        result.add("Docker init schema.sql", FAIL, "File not found")

    if not check_directory_exists("migrations"):
        result.add("migrations/ directory removed", PASS)
    else:
        result.add("migrations/ directory removed", FAIL, "Directory still exists")


def validate_documentation(result: ValidationResult):
    """Validate: Documentation"""
    print("\n[Documentation] Checking docs...")

    docs = [
        ("README.md", "主文档"),
        ("CHANGELOG.md", "变更日志"),
        ("docs/DEPLOYMENT.md", "部署文档"),
    ]

    for doc, desc in docs:
        if check_file_exists(doc):
            result.add(f"Doc: {desc}", PASS)
        else:
            result.add(f"Doc: {desc}", FAIL, f"Missing {doc}")


async def main():
    print("=" * 60)
    print("MEMORY RECALL v5.1.5 - VALIDATION SCRIPT")
    print(f"Run Time: {datetime.now().isoformat()}")
    print("=" * 60)

    result = ValidationResult()

    validate_database_schema(result)
    validate_core_services(result)
    validate_api_endpoints(result)
    validate_initialization(result)
    validate_documentation(result)

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
