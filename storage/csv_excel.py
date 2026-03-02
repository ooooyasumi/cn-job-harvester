"""CSV/Excel 数据存储"""
import pandas as pd
from typing import List
from scrapers.base import Job


class JobStorage:
    """职位数据存储类"""

    @staticmethod
    def to_csv(jobs: List[Job], filepath: str) -> str:
        """保存为 CSV 格式"""
        if not jobs:
            return filepath

        data = [job.__dict__ for job in jobs]
        df = pd.DataFrame(data)

        # 添加序号列（在第一列）
        df.insert(0, '序号', range(1, len(df) + 1))

        df.to_csv(filepath, index=False, encoding='utf-8-sig')
        return filepath

    @staticmethod
    def to_excel(jobs: List[Job], filepath: str) -> str:
        """保存为 Excel 格式"""
        if not jobs:
            return filepath

        data = [job.__dict__ for job in jobs]
        df = pd.DataFrame(data)

        # 确保是 xlsx 格式
        if not filepath.endswith('.xlsx'):
            filepath = filepath.replace('.xls', '') + '.xlsx'

        # 添加序号列（在第一列）
        df.insert(0, '序号', range(1, len(df) + 1))

        df.to_excel(filepath, index=False, engine='openpyxl')
        return filepath

    @staticmethod
    def save(jobs: List[Job], filepath: str, format: str = 'csv') -> str:
        """根据格式保存数据"""
        if format.lower() == 'excel' or filepath.endswith('.xlsx') or filepath.endswith('.xls'):
            return JobStorage.to_excel(jobs, filepath)
        else:
            return JobStorage.to_csv(jobs, filepath)
