from typing import Any
from deepsearcher.rbase.ai_models import ClassifierValue

class ClassifierValueProcess:

    def prompt_value_table(classifier_values: list[ClassifierValue]) -> str:
        return markdown_table_tr(["取值ID", "取值", "取值别名", "取值依据"], is_head=True) + \
            "".join([markdown_table_tr([str(value.id), value.value, value.alias, value.value_clue]) for value in classifier_values])


def markdown_table_tr(columns: list[Any], is_head: bool = False) -> str:
    if is_head:
        return "| " + " | ".join(columns) + " |\n" + "| " + " | ".join(["---"] * len(columns)) + " |\n"
    else:
        return "| " + " | ".join(columns) + " |\n"