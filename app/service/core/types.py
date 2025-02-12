"""
Typing hints for SubmissionManager
"""

from app.db.models import ColumnDef, TableDef, TableView
from app.schemas.column_def import AttributeType

TableViewsData = dict[int, TableView]
TableDefsData = dict[int, TableDef]
ColumnDefsDataByName = dict[str, ColumnDef]
ColumnDefsDataById = dict[int, ColumnDef]
FormRowsData = dict[str, list[dict]]
RecurseAttributeTypes = (
    AttributeType.FORM,
    AttributeType.FORM_OR_NULL,
    AttributeType.MULTIPLE,
)
