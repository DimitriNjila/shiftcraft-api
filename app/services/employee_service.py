import logging

from ..core.db import supabase
from uuid import UUID
from supabase import Client
from typing import List, Optional, Dict, Any

logger = logging.getLogger(__name__)


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
        logger.debug(
            "get_employees called: restaurant_id=%s is_active=%s",
            restaurant_id,
            is_active,
        )
        query = self.supabase.table(self.table_name).select("*")

        if restaurant_id is not None:
            query = query.eq("restaurant_id", restaurant_id)
        if is_active is not None:
            query = query.eq("is_active", is_active)

        query = query.order("name")
        response = query.execute()
        logger.info("Returning %d employees", len(response.data))
        return response.data

    def get_employee_by_id(self, employee_id: UUID) -> Optional[Dict[str, Any]]:
        """
        Get a single employee by ID.

        Args:
            employee_id: UUID of the employee

        Returns:
            Employee dictionary or None if not found
        """
        logger.debug("Looking up employee id=%s", employee_id)
        response = (
            self.supabase.table(self.table_name)
            .select("*")
            .eq("id", str(employee_id))
            .execute()
        )
        if response.data:
            logger.info("Employee found id=%s", employee_id)
            return response.data[0]
        logger.warning("Employee not found id=%s", employee_id)
        return None

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

        logger.info(
            "Creating employee name=%s role=%s restaurant_id=%s",
            name.strip(),
            role.strip(),
            restaurant_id,
        )

        employee_data = {
            "name": name.strip(),
            "role": role.strip(),
            "is_active": is_active,
            "restaurant_id": restaurant_id,
        }

        response = self.supabase.table(self.table_name).insert(employee_data).execute()
        created = response.data[0]
        logger.info("Employee created id=%s", created.get("id"))
        return created

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

        if not update_data:
            logger.warning("update_employee called with no fields to update id=%s", employee_id)
        else:
            logger.info("Updating employee id=%s fields=%s", employee_id, list(update_data.keys()))

        response = (
            self.supabase.table(self.table_name)
            .update(update_data)
            .eq("id", str(employee_id))
            .execute()
        )

        result = response.data[0] if response.data else existing
        logger.info("Employee %s updated", employee_id)
        return result

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

        logger.info("Deleting employee id=%s", employee_id)
        response = (
            self.supabase.table(self.table_name)
            .delete()
            .eq("id", str(employee_id))
            .execute()
        )
        logger.info("Employee deleted id=%s", employee_id)
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
            logger.warning("Employee id=%s is already inactive", employee_id)
            return existing

        logger.info("Deactivating employee id=%s", employee_id)
        result = self.update_employee(employee_id, is_active=False)
        logger.info("Employee deactivated id=%s", employee_id)
        return result


employee_service = EmployeeService(supabase_client=supabase)
