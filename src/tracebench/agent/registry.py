"""Describes each tool to the model, and runs the tool the model asks for."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, Field, ValidationError

from tracebench.agent import tools
from tracebench.llm.types import ToolSpec


class GetCustomerArgs(BaseModel):
    email: str = Field(description="The customer's email address.")


class GetOrderArgs(BaseModel):
    order_id: int = Field(description="The order number, e.g. 1042.")
    customer_email: str = Field(description="The email address of the customer asking.")


class CheckInventoryArgs(BaseModel):
    product: str = Field(
        description="A product SKU, or words from the product name, e.g. '30 lb kibble'."
    )


class SearchPoliciesArgs(BaseModel):
    query: str = Field(description="A short search query, e.g. 'return opened food'.")


class IssueRefundArgs(BaseModel):
    order_id: int = Field(description="The order number to refund.")
    customer_email: str = Field(description="The email address of the customer asking.")
    amount_usd: float = Field(gt=0, description="The refund amount in US dollars, e.g. 24.99.")
    reason: str = Field(description="A short reason for the refund.")


class EscalateArgs(BaseModel):
    reason: str = Field(description="Why this case needs a human specialist.")
    customer_email: str | None = Field(default=None, description="The customer's email, if known.")
    order_id: int | None = Field(default=None, description="The related order number, if any.")


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    args_model: type[BaseModel]
    function: Callable[..., dict]

    def spec(self) -> ToolSpec:
        return ToolSpec(
            name=self.name,
            description=self.description,
            parameters=self.args_model.model_json_schema(),
        )


TOOLS = [
    Tool(
        name="get_customer",
        description=(
            "Look up a customer by email address. Returns their name, loyalty tier "
            "(standard or gold), and a list of their orders."
        ),
        args_model=GetCustomerArgs,
        function=tools.get_customer,
    ),
    Tool(
        name="get_order",
        description=(
            "Get full details of one order: status, dates, items with prices, and how "
            "much has already been refunded. Only returns orders that belong to the "
            "given email."
        ),
        args_model=GetOrderArgs,
        function=tools.get_order,
    ),
    Tool(
        name="check_inventory",
        description=(
            "Check stock for a product by SKU or by words from its name. Returns "
            "whether it is in stock and the estimated restock date, if there is one."
        ),
        args_model=CheckInventoryArgs,
        function=tools.check_inventory,
    ),
    Tool(
        name="search_policies",
        description=(
            "Search the store's policies. Returns up to 3 relevant policies with their "
            "full text. Use it before answering any question about returns, refunds, "
            "damage, shipping, cancellations, prescriptions, loyalty, Autoship, or "
            "privacy."
        ),
        args_model=SearchPoliciesArgs,
        function=tools.search_policies,
    ),
    Tool(
        name="issue_refund",
        description=(
            "Issue a refund on a delivered order. Only use it after checking the order "
            "details and the relevant policies. Total refunds over $100.00 per order "
            "are not allowed; escalate those instead."
        ),
        args_model=IssueRefundArgs,
        function=tools.issue_refund,
    ),
    Tool(
        name="escalate_to_human",
        description=(
            "Hand the case to a human specialist. Use it when a policy says to "
            "escalate, or when the customer asks for a human."
        ),
        args_model=EscalateArgs,
        function=tools.escalate_to_human,
    ),
]

TOOLS_BY_NAME = {tool.name: tool for tool in TOOLS}


def tool_specs() -> list[ToolSpec]:
    """The menu: a description of every tool, ready to send to the model."""
    return [tool.spec() for tool in TOOLS]


def run_tool(name: str, arguments: dict[str, Any]) -> dict:
    """Check the model's request, then run the tool. Never crashes: problems come back as errors."""
    tool = TOOLS_BY_NAME.get(name)
    if tool is None:
        available = ", ".join(TOOLS_BY_NAME)
        return {"error": f"Unknown tool '{name}'. Available tools: {available}."}

    try:
        args = tool.args_model.model_validate(arguments)
    except ValidationError as error:
        problems = "; ".join(
            f"{'.'.join(str(part) for part in problem['loc'])}: {problem['msg']}"
            for problem in error.errors()
        )
        return {"error": f"Invalid arguments for {name}: {problems}"}

    try:
        return tool.function(**args.model_dump())
    except Exception as error:
        return {"error": f"Tool {name} failed unexpectedly: {error}"}


if __name__ == "__main__":
    import json

    print("=== The menu item for get_order ===")
    print(json.dumps(TOOLS_BY_NAME["get_order"].spec().model_dump(), indent=2))

    email = "chloe.garcia1@example.com"
    examples = {
        "order_id as text '1001' (gets fixed)": run_tool(
            "get_order", {"order_id": "1001", "customer_email": email}
        ),
        "order_id 'abc' (invalid)": run_tool(
            "get_order", {"order_id": "abc", "customer_email": email}
        ),
        "missing customer_email": run_tool("get_order", {"order_id": 1001}),
        "negative refund": run_tool(
            "issue_refund",
            {"order_id": 1001, "customer_email": email, "amount_usd": -5, "reason": "Test"},
        ),
        "a tool that doesn't exist": run_tool("fly_to_the_moon", {}),
    }
    for title, result in examples.items():
        print(f"\n=== {title} ===")
        print(json.dumps(result, indent=2, ensure_ascii=False)[:400])