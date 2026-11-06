# -*- coding: utf-8 -*-
"""reporting — فاز ۵: خروجی‌های Word/PDF/Excel و GIS.

The exporters consume ONE neutral content tree (`content.build_report`)
built from a `StudyModel`, so Word, PDF and Excel always carry the same
numbers (single source of truth — D-04 philosophy applied to reports).

- model       : StudyModel — network + topology + placement snapshot
- content     : neutral Persian report content (sections/tables/KPIs)
- workbook    : openpyxl RTL workbook (فاز ۵)
- docx_report : python-docx RTL engineering report + map image
- pdf_report  : ReportLab PDF (Vazirmatn + arabic_reshaper + python-bidi)
- gis_export  : GeoJSON (network / switches+proposed / zones) + CSV schedule
- service     : ReportService — orchestration + cross-check vs DB
"""
