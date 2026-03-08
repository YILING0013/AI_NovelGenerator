# -*- coding: utf-8 -*-
"""
安全临时文件清理脚本
分层清理策略，确保不误删重要文件
"""
import os
import shutil
import glob
from datetime import datetime, timedelta

def safe_cleanup():
    """执行安全的临时文件清理"""

    # 创建清理日志
    cleanup_log = []

    print("🧹 开始安全清理临时文件...")

    # 第1层：清理Python缓存（最安全）
    print("\n📂 第1层：清理Python缓存文件")
    pycache_count = 0
    for root, dirs, files in os.walk('.'):
        if '__pycache__' in dirs:
            pycache_path = os.path.join(root, '__pycache__')
            try:
                shutil.rmtree(pycache_path)
                pycache_count += 1
                print(f"  ✅ 删除: {pycache_path}")
                cleanup_log.append(f"删除缓存目录: {pycache_path}")
            except Exception as e:
                print(f"  ❌ 删除失败: {pycache_path} - {e}")

    print(f"  📊 清理了 {pycache_count} 个缓存目录")

    # 第2层：清理测试结果文件
    print("\n📊 第2层：清理测试结果文件")
    temp_patterns = [
        "temp_results_*.json",
        "temp_*.json",
        "temp_*.txt"
    ]

    temp_count = 0
    for pattern in temp_patterns:
        for file_path in glob.glob(pattern):
            try:
                os.remove(file_path)
                temp_count += 1
                print(f"  ✅ 删除: {file_path}")
                cleanup_log.append(f"删除临时文件: {file_path}")
            except Exception as e:
                print(f"  ❌ 删除失败: {file_path} - {e}")

    print(f"  📊 清理了 {temp_count} 个临时结果文件")

    # 第3层：清理旧日志文件（保留最近的）
    print("\n📝 第3层：清理旧日志文件")
    log_files = []
    for log_file in glob.glob("*.log"):
        try:
            mtime = os.path.getmtime(log_file)
            log_files.append((log_file, mtime))
        except:
            continue

    # 按修改时间排序，保留最新的5个
    log_files.sort(key=lambda x: x[1], reverse=True)
    keep_logs = set([log_files[i][0] for i in range(min(5, len(log_files)))])

    log_count = 0
    for log_file, _ in log_files:
        if log_file not in keep_logs:
            try:
                os.remove(log_file)
                log_count += 1
                print(f"  ✅ 删除: {log_file}")
                cleanup_log.append(f"删除日志文件: {log_file}")
            except Exception as e:
                print(f"  ❌ 删除失败: {log_file} - {e}")

    print(f"  📊 清理了 {log_count} 个旧日志文件")
    print(f"  📋 保留了: {', '.join(list(keep_logs)[:5])}")

    # 第4层：清理HTML测试报告（可重新生成）
    print("\n📋 第4层：清理测试报告目录")
    report_dirs = ['htmlcov', 'test_reports', '.pytest_cache']

    report_count = 0
    for report_dir in report_dirs:
        if os.path.exists(report_dir):
            try:
                shutil.rmtree(report_dir)
                report_count += 1
                print(f"  ✅ 删除: {report_dir}/")
                cleanup_log.append(f"删除报告目录: {report_dir}")
            except Exception as e:
                print(f"  ❌ 删除失败: {report_dir} - {e}")

    print(f"  📊 清理了 {report_count} 个测试报告目录")

    # 第5层：备份文件（仅清理时间戳重复的）
    print("\n💾 第5层：清理重复备份文件")
    backup_groups = {}

    # 按原文件分组备份
    for backup_file in glob.glob("*.backup*"):
        if '.backup_' in backup_file:
            # 提取原文件名
            original = backup_file.split('.backup_')[0]
            if original not in backup_groups:
                backup_groups[original] = []
            backup_groups[original].append(backup_file)

    backup_count = 0
    for original, backups in backup_groups.items():
        if len(backups) > 2:  # 保留最新的2个备份
            # 按文件名排序（时间戳在文件名中）
            backups.sort(reverse=True)
            for old_backup in backups[2:]:
                try:
                    os.remove(old_backup)
                    backup_count += 1
                    print(f"  ✅ 删除: {old_backup}")
                    cleanup_log.append(f"删除旧备份: {old_backup}")
                except Exception as e:
                    print(f"  ❌ 删除失败: {old_backup} - {e}")

    print(f"  📊 清理了 {backup_count} 个重复备份文件")

    # 生成清理报告
    print("\n📄 生成清理报告...")
    report_time = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_file = f"cleanup_report_{report_time}.txt"

    with open(report_file, 'w', encoding='utf-8') as f:
        f.write(f"临时文件清理报告\n")
        f.write(f"清理时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"清理统计:\n")
        f.write(f"  - Python缓存目录: {pycache_count} 个\n")
        f.write(f"  - 临时结果文件: {temp_count} 个\n")
        f.write(f"  - 旧日志文件: {log_count} 个\n")
        f.write(f"  - 测试报告目录: {report_count} 个\n")
        f.write(f"  - 重复备份文件: {backup_count} 个\n")
        f.write(f"\n清理详情:\n")
        for item in cleanup_log:
            f.write(f"  {item}\n")

    print(f"  ✅ 清理报告已保存: {report_file}")

    # 总结
    total_cleaned = pycache_count + temp_count + log_count + report_count + backup_count
    print(f"\n🎉 清理完成！")
    print(f"📊 总计清理: {total_cleaned} 个文件/目录")
    print(f"📋 详细报告: {report_file}")

    return total_cleaned

if __name__ == "__main__":
    safe_cleanup()