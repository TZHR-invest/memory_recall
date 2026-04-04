#!/usr/bin/env python3
"""
实体表脏数据清理脚本

功能:
- 删除黑名单匹配的实体
- 删除文件路径格式实体
- 删除纯数值实体
- 删除过长/过短实体
- 提供预览模式 (dry-run)
- 创建备份文件
- 生成清理报告

用法:
    python cleanup_entities.py --dry-run           # 预览待删除实体
    python cleanup_entities.py --confirm           # 执行清理
    python cleanup_entities.py --backup-dir ./backups  # 指定备份目录
"""

import argparse
import asyncio
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.database import db


MEANINGLESS_ENTITIES = {
    "我",
    "你",
    "他",
    "她",
    "它",
    "我们",
    "你们",
    "他们",
    "自己",
    "大家",
    "用户",
    "说话者",
    "作者",
    "读者",
    "目前",
    "平时",
    "最近",
    "现在",
    "当前",
    "近期",
    "将来",
    "过去",
    "一个",
    "几个",
    "一些",
    "很多",
    "少量",
    "多个",
    "各种",
    "所有",
    "就",
    "也",
    "都",
    "还",
    "又",
    "才",
    "只",
    "最",
    "很",
    "非常",
    "代码",
    "技术",
    "日志",
    "数据库",
    "系统",
    "项目",
    "功能",
    "服务",
    "接口",
    "模块",
    "组件",
    "文件",
    "配置",
    "数据",
    "信息",
    "内容",
    "问题",
    "方案",
    "方法",
    "方式",
    "模式",
    "架构",
    "设计",
    "实现",
    "中文",
    "英文",
    "英文版",
    "中文版",
    "EN",
    "CN",
    "中断",
    "新建",
    "关联",
    "修正",
    "延后",
    "完成",
    "进行中",
    "待处理",
    "博客",
    "微信",
    "微博",
    "网站",
    "app",
    "APP",
    "AI",
    "UI",
    "API",
}

SKIP_ENTITY_TYPES = {"time", "number", "activity"}


def should_skip_entity(name: str) -> bool:
    if not name:
        return True
    name = name.strip()
    if len(name) < 2 or len(name) > 20:
        return True
    if re.match(r"^[\d.]+$", name):
        return True
    if re.match(r"^[a-zA-Z0-9_\-./]+$", name):
        if "/" in name or name.count(".") > 1:
            return True
    if re.match(r"^[\w.]+:\d+", name):
        return True
    return False


async def get_entity_stats() -> Dict[str, Any]:
    total = await db.fetchval("SELECT COUNT(*) FROM entities")
    by_type = await db.fetch(
        "SELECT type, COUNT(*) as count FROM entities GROUP BY type ORDER BY count DESC"
    )
    return {"total": total, "by_type": {row["type"]: row["count"] for row in by_type}}


async def find_blacklist_entities() -> List[Dict[str, Any]]:
    placeholders = ", ".join(f"'{name}'" for name in MEANINGLESS_ENTITIES)
    query = f"""
        SELECT id, name, type, container_tag, mention_count
        FROM entities
        WHERE LOWER(TRIM(name)) IN ({placeholders})
        ORDER BY name
    """
    return await db.fetch(query)


async def find_file_path_entities() -> List[Dict[str, Any]]:
    query = """
        SELECT id, name, type, container_tag, mention_count
        FROM entities
        WHERE name ~ '^[a-zA-Z0-9_\\-./]+$'
          AND (name LIKE '%/%' OR name ~ '\\.[a-z]{2,4}$')
        ORDER BY name
    """
    return await db.fetch(query)


async def find_numeric_entities() -> List[Dict[str, Any]]:
    query = """
        SELECT id, name, type, container_tag, mention_count
        FROM entities
        WHERE name ~ '^[0-9.]+$'
        ORDER BY name
    """
    return await db.fetch(query)


async def find_length_invalid_entities() -> List[Dict[str, Any]]:
    query = """
        SELECT id, name, type, container_tag, mention_count
        FROM entities
        WHERE LENGTH(name) < 2 OR LENGTH(name) > 20
        ORDER BY LENGTH(name) DESC
    """
    return await db.fetch(query)


async def delete_entities(entity_ids: List[str]) -> int:
    if not entity_ids:
        return 0

    placeholders = ", ".join(f"'{eid}'" for eid in entity_ids)

    await db.execute(f"DELETE FROM memory_entities WHERE entity_id IN ({placeholders})")
    await db.execute(
        f"DELETE FROM entity_relations WHERE from_entity_id IN ({placeholders}) OR to_entity_id IN ({placeholders})"
    )

    result = await db.execute(f"DELETE FROM entities WHERE id IN ({placeholders})")
    return int(result.split()[-1]) if result else 0


async def create_backup(backup_dir: str) -> str:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_file = os.path.join(backup_dir, f"entities_backup_{timestamp}.sql")

    os.makedirs(backup_dir, exist_ok=True)

    entities = await db.fetch("SELECT * FROM entities")
    memory_entities = await db.fetch("SELECT * FROM memory_entities")
    entity_relations = await db.fetch("SELECT * FROM entity_relations")

    with open(backup_file, "w", encoding="utf-8") as f:
        f.write(f"-- Entity Backup created at {datetime.now().isoformat()}\n\n")

        f.write("-- Entities\n")
        for row in entities:
            values = []
            for key, val in row.items():
                if val is None:
                    values.append("NULL")
                elif isinstance(val, str):
                    escaped = val.replace("'", "''")
                    values.append(f"'{escaped}'")
                else:
                    values.append(str(val))
            f.write(f"INSERT INTO entities VALUES ({', '.join(values)});\n")

        f.write("\n-- Memory Entities\n")
        for row in memory_entities:
            values = []
            for key, val in row.items():
                if val is None:
                    values.append("NULL")
                elif isinstance(val, str):
                    escaped = val.replace("'", "''")
                    values.append(f"'{escaped}'")
                else:
                    values.append(str(val))
            f.write(f"INSERT INTO memory_entities VALUES ({', '.join(values)});\n")

        f.write("\n-- Entity Relations\n")
        for row in entity_relations:
            values = []
            for key, val in row.items():
                if val is None:
                    values.append("NULL")
                elif isinstance(val, str):
                    escaped = val.replace("'", "''")
                    values.append(f"'{escaped}'")
                else:
                    values.append(str(val))
            f.write(f"INSERT INTO entity_relations VALUES ({', '.join(values)});\n")

    return backup_file


def print_report(before_stats: Dict, after_stats: Dict, deleted_counts: Dict):
    print("\n" + "=" * 60)
    print("实体清理报告")
    print("=" * 60)

    print(f"\n清理前总数: {before_stats['total']}")
    print(f"清理后总数: {after_stats['total']}")
    print(f"总计删除: {before_stats['total'] - after_stats['total']}")

    print("\n按类型统计:")
    print(f"{'类型':<15} {'清理前':>10} {'清理后':>10} {'删除':>10}")
    print("-" * 50)

    all_types = set(before_stats["by_type"].keys()) | set(after_stats["by_type"].keys())
    for entity_type in sorted(all_types):
        before = before_stats["by_type"].get(entity_type, 0)
        after = after_stats["by_type"].get(entity_type, 0)
        deleted = before - after
        print(f"{entity_type:<15} {before:>10} {after:>10} {deleted:>10}")

    print("\n删除分类统计:")
    for category, count in deleted_counts.items():
        print(f"  {category}: {count}")


def print_preview(category: str, entities: List[Dict[str, Any]], limit: int = 20):
    print(f"\n{category} ({len(entities)} 条):")
    print("-" * 80)

    for i, entity in enumerate(entities[:limit]):
        print(
            f"  [{entity['id']}] {entity['name']} ({entity['type']}) - {entity['container_tag'][:30]}"
        )

    if len(entities) > limit:
        print(f"  ... 还有 {len(entities) - limit} 条")


async def main():
    parser = argparse.ArgumentParser(description="实体表脏数据清理脚本")
    parser.add_argument("--dry-run", action="store_true", help="预览模式，不执行删除")
    parser.add_argument("--confirm", action="store_true", help="确认执行清理")
    parser.add_argument("--backup-dir", default="./backups", help="备份目录")

    args = parser.parse_args()

    if not args.dry_run and not args.confirm:
        print("错误: 必须指定 --dry-run 或 --confirm")
        print("\n用法:")
        print("  python cleanup_entities.py --dry-run    # 预览待删除实体")
        print("  python cleanup_entities.py --confirm    # 执行清理")
        sys.exit(1)

    print("=" * 60)
    print("实体表脏数据清理")
    print("=" * 60)

    before_stats = await get_entity_stats()
    print(f"\n当前实体总数: {before_stats['total']}")

    blacklist_entities = await find_blacklist_entities()
    file_path_entities = await find_file_path_entities()
    numeric_entities = await find_numeric_entities()
    length_invalid_entities = await find_length_invalid_entities()

    all_entity_ids = set()
    for entities in [
        blacklist_entities,
        file_path_entities,
        numeric_entities,
        length_invalid_entities,
    ]:
        for entity in entities:
            all_entity_ids.add(str(entity["id"]))

    print(f"\n待删除实体总数: {len(all_entity_ids)}")

    if args.dry_run:
        print("\n【预览模式】以下实体将被删除:")
        print_preview("黑名单实体", blacklist_entities)
        print_preview("文件路径实体", file_path_entities)
        print_preview("纯数值实体", numeric_entities)
        print_preview("长度异常实体", length_invalid_entities)

        print(f"\n提示: 使用 --confirm 执行清理")

    elif args.confirm:
        backup_file = await create_backup(args.backup_dir)
        print(f"\n备份已创建: {backup_file}")

        print("\n确认删除 {} 个实体? [y/N]: ".format(len(all_entity_ids)), end="")
        confirmation = input().strip().lower()

        if confirmation != "y":
            print("已取消清理")
            sys.exit(0)

        print("\n正在清理...")
        deleted_count = await delete_entities(list(all_entity_ids))

        after_stats = await get_entity_stats()

        deleted_counts = {
            "黑名单实体": len(blacklist_entities),
            "文件路径实体": len(file_path_entities),
            "纯数值实体": len(numeric_entities),
            "长度异常实体": len(length_invalid_entities),
        }

        print_report(before_stats, after_stats, deleted_counts)
        print(f"\n清理完成! 共删除 {deleted_count} 个实体")


if __name__ == "__main__":
    asyncio.run(main())
