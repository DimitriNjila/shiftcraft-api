from ..core.db import supabase
from uuid import UUID
from supabase import Client
from typing import List, Optional, Dict, Any


class EmployeeNotFoundError(Exception):
    """
    Raised when an employee is not found
    """

    def __init__(self, employee_id: UUID):
        self.employee_id = employee_id
        super().__init__(f"Employee with ID {employee_id} not found")


class EmployeeService:
    """Service for managing restaurant employees"""

    def __init__(self, supabase_client: Client):
        self.supabase = supabase_client
        self.table_name = "employees"

    def get_employees(
        self, restaurant_id: Optional[str] = None, is_active: Optional[bool] = None
    ) -> List[Dict[str, Any]]:
        """
        Get all employees with optional filtering.

        Args:
            restaurant_id: Filter by restaurant (for future multi-tenant support)
            is_active: Filter by active status (True/False/None for all)

        Returns:
            List of employee dictionaries
        """
        query = self.supabase.table(self.table_name).select("*")

        if restaurant_id is not None:
            query = query.eq("restaurant_id", restaurant_id)
        if is_active is not None:
            query = query.eq("is_active", is_active)

        query = query.order("name")
        response = query.execute()
        return response.data

    def get_employee_by_id(self, employee_id: UUID) -> Optional[Dict[str, Any]]:
        """
        Get a single employee by ID.

        Args:
            employee_id: UUID of the employee

        Returns:
            Employee dictionary or None if not found
        """
        response = (
            self.supabase.table(self.table_name)
            .select("*")
            .eq("id", str(employee_id))
            .execute()
        )
        return response.data[0] if response.data else None

    def create_employee(
        self,
        name: str,
        role: str,
        is_active: bool = True,
        restaurant_id: str = None,
    ) -> Dict[str, Any]:
        """
        Create a new employee.

        Args:
            name: Employee name
            role: Employee role
            is_active: Active status
            restaurant_id: Associated restaurant ID

        Returns:
            Created employee dictionary

        Raises:
            ValueError: If required fields are invalid
        """
        # Input validation
        if not name or not name.strip():
            raise ValueError("Employee name cannot be empty")

        if not role or not role.strip():
            raise ValueError("Employee role cannot be empty")

        if not restaurant_id:
            raise ValueError("Restaurant ID is required")

        employee_data = {
            "name": name.strip(),
            "role": role.strip(),
            "is_active": is_active,
            "restaurant_id": restaurant_id,
        }

        response = self.supabase.table(self.table_name).insert(employee_data).execute()
        return response.data[0]

    def update_employee(
        self,
        employee_id: UUID,
        name: Optional[str] = None,
        role: Optional[str] = None,
        is_active: Optional[bool] = None,
        email: Optional[str] = None,
        deleted_at: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Update an existing employee.

        Args:
            employee_id: UUID of the employee to update
            name: New name (optional)
            role: New role (optional)
            is_active: New active status (optional)
            email: New email (optional)
            deleted_at: Deletion timestamp (optional)

        Returns:
            Updated employee dictionary

        Raises:
            EmployeeNotFoundError: If the employee does not exist
            ValueError: If update data is invalid
        """
        # Check if employee exists first
        existing = self.get_employee_by_id(employee_id)
        if not existing:
            raise EmployeeNotFoundError(employee_id)

        update_data = {}
        if name is not None:
            update_data["name"] = name
        if role is not None:
            update_data["role"] = role
        if is_active is not None:
            update_data["is_active"] = is_active
        if email is not None:
            update_data["email"] = email
        if deleted_at is not None:
            update_data["deleted_at"] = deleted_at

        response = (
            self.supabase.table(self.table_name)
            .update(update_data)
            .eq("id", str(employee_id))
            .execute()
        )

        return response.data[0] if response.data else existing

    def delete_employee(self, employee_id: UUID) -> Dict[str, Any]:
        """
        Delete an employee (hard delete).

        Args:
            employee_id: UUID of the employee to delete

        Returns:
            Deleted employee dictionary

        Raises:
            EmployeeNotFoundError: If the employee does not exist
        """
        # Check if employee exists first
        existing = self.get_employee_by_id(employee_id)
        if not existing:
            raise EmployeeNotFoundError(employee_id)

        response = (
            self.supabase.table(self.table_name)
            .delete()
            .eq("id", str(employee_id))
            .execute()
        )
        return response.data[0] if response.data else existing

    def deactivate_employee(self, employee_id: UUID) -> Dict[str, Any]:
        """
        Deactivate an employee (soft delete).

        Args:
            employee_id: UUID of the employee to deactivate

        Returns:
            Updated employee dictionary

        Raises:
            EmployeeNotFoundError: If the employee does not exist
        """
        # check if employee is already deactivated
        existing = self.get_employee_by_id(employee_id)
        if not existing:
            raise EmployeeNotFoundError(employee_id)

        if not existing.get("is_active", True):
            # Employee is already deactivated
            return existing

        return self.update_employee(employee_id, is_active=False)


employee_service = EmployeeService(supabase_client=supabase)
