from ..core.db import supabase


def get_employees():
    response = supabase.table("employees").select("*").execute()
    if response.error:
        raise Exception(f"Error fetching employees: {response.error.message}")
    return response.data


def get_employee_by_id(employee_id: int):
    response = supabase.table("employees").select("*").eq("id", employee_id).execute()
    if response.error:
        raise Exception(
            f"Error fetching employee with ID {employee_id}: {response.error.message}"
        )
    return response.data[0] if response.data else None


def create_employee(name: str, role: str, is_active: bool = True):
    response = (
        supabase.table("employees")
        .insert({"name": name, "role": role, "is_active": is_active})
        .execute()
    )
    if response.error:
        raise Exception(f"Error creating employee: {response.error.message}")
    return response.data[0]


def update_employee(
    employee_id: int, name: str = None, role: str = None, is_active: bool = None
):
    update_data = {}
    if name is not None:
        update_data["name"] = name
    if role is not None:
        update_data["role"] = role
    if is_active is not None:
        update_data["is_active"] = is_active

    response = (
        supabase.table("employees").update(update_data).eq("id", employee_id).execute()
    )
    if response.error:
        raise Exception(
            f"Error updating employee with ID {employee_id}: {response.error.message}"
        )
    return response.data[0]


def delete_employee(employee_id: int):
    response = supabase.table("employees").delete().eq("id", employee_id).execute()
    if response.error:
        raise Exception(
            f"Error deleting employee with ID {employee_id}: {response.error.message}"
        )
    return response.data[0]
