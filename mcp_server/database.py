"""
Database Manager for Customer Support System (GIVEN - fully implemented)
Handles all database operations for customers and tickets tables
"""

import sqlite3
import logging
from datetime import datetime
from typing import Dict, List, Optional, Any
from contextlib import contextmanager

logger = logging.getLogger(__name__)


class DatabaseManager:
    """Manages database operations for customer support system."""

    def __init__(self, db_path: str):
        """
        Initialize the DatabaseManager.

        Args:
            db_path: Path to the SQLite database file
        """
        self.db_path = db_path
        self.initialize_database()

    @contextmanager
    def get_connection(self):
        """Context manager for database connections."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            yield conn
            conn.commit()
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            conn.close()

    def initialize_database(self):
        """Create tables and indexes if they don't exist."""
        with self.get_connection() as conn:
            cursor = conn.cursor()

            # Create customers table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS customers (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    email TEXT,
                    phone TEXT,
                    status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active', 'disabled')),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Create tickets table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS tickets (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    customer_id INTEGER NOT NULL,
                    issue TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'open' CHECK(status IN ('open', 'in_progress', 'resolved')),
                    priority TEXT NOT NULL DEFAULT 'medium' CHECK(priority IN ('low', 'medium', 'high')),
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (customer_id) REFERENCES customers(id) ON DELETE CASCADE
                )
            """)

            # Create indexes
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_customers_email ON customers(email)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_customers_status ON customers(status)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_tickets_customer_id ON tickets(customer_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_tickets_status ON tickets(status)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_tickets_priority ON tickets(priority)")

            # Create trigger for updated_at
            cursor.execute("""
                CREATE TRIGGER IF NOT EXISTS update_customer_timestamp
                AFTER UPDATE ON customers
                FOR EACH ROW
                BEGIN
                    UPDATE customers SET updated_at = CURRENT_TIMESTAMP WHERE id = NEW.id;
                END
            """)

            logger.info("Database initialized successfully")

    # ==================== Customer Operations ====================

    def get_customer(self, customer_id: int) -> Optional[Dict[str, Any]]:
        """
        Get a customer by ID.

        Args:
            customer_id: The customer's ID

        Returns:
            Dictionary with customer data or None if not found
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM customers WHERE id = ?", (customer_id,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def list_customers(self, status: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        List all customers, optionally filtered by status.

        Args:
            status: Optional status filter ('active' or 'disabled')

        Returns:
            List of customer dictionaries
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            if status:
                cursor.execute("SELECT * FROM customers WHERE status = ? ORDER BY name", (status,))
            else:
                cursor.execute("SELECT * FROM customers ORDER BY name")
            return [dict(row) for row in cursor.fetchall()]

    def add_customer(self, name: str, email: Optional[str] = None,
                    phone: Optional[str] = None, status: str = 'active') -> Dict[str, Any]:
        """
        Add a new customer.

        Args:
            name: Customer's name
            email: Customer's email
            phone: Customer's phone number
            status: Customer status ('active' or 'disabled')

        Returns:
            The newly created customer dictionary
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO customers (name, email, phone, status) VALUES (?, ?, ?, ?)",
                (name, email, phone, status)
            )
            customer_id = cursor.lastrowid
            logger.info(f"Created customer with ID: {customer_id}")
            return self.get_customer(customer_id)

    def update_customer(self, customer_id: int, name: Optional[str] = None,
                       email: Optional[str] = None, phone: Optional[str] = None) -> Dict[str, Any]:
        """
        Update customer information.

        Args:
            customer_id: The customer's ID
            name: New name (optional)
            email: New email (optional)
            phone: New phone (optional)

        Returns:
            The updated customer dictionary

        Raises:
            ValueError: If customer not found
        """
        customer = self.get_customer(customer_id)
        if not customer:
            raise ValueError(f"Customer with ID {customer_id} not found")

        updates = []
        params = []

        if name is not None:
            updates.append("name = ?")
            params.append(name)
        if email is not None:
            updates.append("email = ?")
            params.append(email)
        if phone is not None:
            updates.append("phone = ?")
            params.append(phone)

        if not updates:
            return customer

        params.append(customer_id)
        query = f"UPDATE customers SET {', '.join(updates)} WHERE id = ?"

        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            logger.info(f"Updated customer ID: {customer_id}")
            return self.get_customer(customer_id)

    def disable_customer(self, customer_id: int) -> Dict[str, Any]:
        """
        Disable a customer account.

        Args:
            customer_id: The customer's ID

        Returns:
            The updated customer dictionary

        Raises:
            ValueError: If customer not found
        """
        customer = self.get_customer(customer_id)
        if not customer:
            raise ValueError(f"Customer with ID {customer_id} not found")

        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE customers SET status = 'disabled' WHERE id = ?", (customer_id,))
            logger.info(f"Disabled customer ID: {customer_id}")
            return self.get_customer(customer_id)

    def activate_customer(self, customer_id: int) -> Dict[str, Any]:
        """
        Activate a customer account.

        Args:
            customer_id: The customer's ID

        Returns:
            The updated customer dictionary

        Raises:
            ValueError: If customer not found
        """
        customer = self.get_customer(customer_id)
        if not customer:
            raise ValueError(f"Customer with ID {customer_id} not found")

        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE customers SET status = 'active' WHERE id = ?", (customer_id,))
            logger.info(f"Activated customer ID: {customer_id}")
            return self.get_customer(customer_id)

    # ==================== Ticket Operations ====================

    def get_ticket(self, ticket_id: int) -> Optional[Dict[str, Any]]:
        """
        Get a ticket by ID with customer information.

        Args:
            ticket_id: The ticket's ID

        Returns:
            Dictionary with ticket and customer data or None if not found
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT t.*, c.name as customer_name, c.email as customer_email,
                       c.phone as customer_phone, c.status as customer_status
                FROM tickets t
                JOIN customers c ON t.customer_id = c.id
                WHERE t.id = ?
            """, (ticket_id,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def list_tickets(self, status: Optional[str] = None, priority: Optional[str] = None,
                    customer_id: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        List tickets with optional filters.

        Args:
            status: Filter by status ('open', 'in_progress', 'resolved')
            priority: Filter by priority ('low', 'medium', 'high')
            customer_id: Filter by customer ID

        Returns:
            List of ticket dictionaries with customer info
        """
        query = """
            SELECT t.*, c.name as customer_name, c.email as customer_email,
                   c.phone as customer_phone, c.status as customer_status
            FROM tickets t
            JOIN customers c ON t.customer_id = c.id
            WHERE 1=1
        """
        params = []

        if status:
            query += " AND t.status = ?"
            params.append(status)
        if priority:
            query += " AND t.priority = ?"
            params.append(priority)
        if customer_id:
            query += " AND t.customer_id = ?"
            params.append(customer_id)

        query += """ ORDER BY
            CASE t.priority
                WHEN 'high' THEN 1
                WHEN 'medium' THEN 2
                WHEN 'low' THEN 3
            END, t.created_at DESC
        """

        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            return [dict(row) for row in cursor.fetchall()]

    def create_ticket(self, customer_id: int, issue: str,
                     priority: str = 'medium', status: str = 'open') -> Dict[str, Any]:
        """
        Create a new ticket.

        Args:
            customer_id: The customer's ID
            issue: Description of the issue
            priority: Ticket priority ('low', 'medium', 'high')
            status: Ticket status ('open', 'in_progress', 'resolved')

        Returns:
            The newly created ticket dictionary

        Raises:
            ValueError: If customer not found or invalid priority/status
        """
        # Validate customer exists
        customer = self.get_customer(customer_id)
        if not customer:
            raise ValueError(f"Customer with ID {customer_id} not found")

        # Validate priority and status
        if priority not in ['low', 'medium', 'high']:
            raise ValueError(f"Invalid priority: {priority}")
        if status not in ['open', 'in_progress', 'resolved']:
            raise ValueError(f"Invalid status: {status}")

        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO tickets (customer_id, issue, priority, status) VALUES (?, ?, ?, ?)",
                (customer_id, issue, priority, status)
            )
            ticket_id = cursor.lastrowid
            logger.info(f"Created ticket with ID: {ticket_id}")

        # Get the ticket after the transaction is committed
        return self.get_ticket(ticket_id)

    def update_ticket_status(self, ticket_id: int, status: str) -> Dict[str, Any]:
        """
        Update ticket status.

        Args:
            ticket_id: The ticket's ID
            status: New status ('open', 'in_progress', 'resolved')

        Returns:
            The updated ticket dictionary

        Raises:
            ValueError: If ticket not found or invalid status
        """
        ticket = self.get_ticket(ticket_id)
        if not ticket:
            raise ValueError(f"Ticket with ID {ticket_id} not found")

        if status not in ['open', 'in_progress', 'resolved']:
            raise ValueError(f"Invalid status: {status}")

        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE tickets SET status = ? WHERE id = ?", (status, ticket_id))
            logger.info(f"Updated ticket ID {ticket_id} status to: {status}")
            return self.get_ticket(ticket_id)

    def update_ticket_priority(self, ticket_id: int, priority: str) -> Dict[str, Any]:
        """
        Update ticket priority.

        Args:
            ticket_id: The ticket's ID
            priority: New priority ('low', 'medium', 'high')

        Returns:
            The updated ticket dictionary

        Raises:
            ValueError: If ticket not found or invalid priority
        """
        ticket = self.get_ticket(ticket_id)
        if not ticket:
            raise ValueError(f"Ticket with ID {ticket_id} not found")

        if priority not in ['low', 'medium', 'high']:
            raise ValueError(f"Invalid priority: {priority}")

        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE tickets SET priority = ? WHERE id = ?", (priority, ticket_id))
            logger.info(f"Updated ticket ID {ticket_id} priority to: {priority}")
            return self.get_ticket(ticket_id)

    def delete_ticket(self, ticket_id: int) -> bool:
        """
        Delete a ticket.

        Args:
            ticket_id: The ticket's ID

        Returns:
            True if deleted, False if not found
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM tickets WHERE id = ?", (ticket_id,))
            deleted = cursor.rowcount > 0
            if deleted:
                logger.info(f"Deleted ticket ID: {ticket_id}")
            return deleted

    # ==================== Statistics and Reporting ====================

    def get_ticket_stats(self) -> Dict[str, Any]:
        """
        Get ticket statistics.

        Returns:
            Dictionary with ticket counts by status and priority
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()

            # Get counts by status
            cursor.execute("""
                SELECT status, COUNT(*) as count
                FROM tickets
                GROUP BY status
            """)
            status_counts = {row['status']: row['count'] for row in cursor.fetchall()}

            # Get counts by priority
            cursor.execute("""
                SELECT priority, COUNT(*) as count
                FROM tickets
                GROUP BY priority
            """)
            priority_counts = {row['priority']: row['count'] for row in cursor.fetchall()}

            # Get total count
            cursor.execute("SELECT COUNT(*) as total FROM tickets")
            total = cursor.fetchone()['total']

            return {
                'total_tickets': total,
                'by_status': status_counts,
                'by_priority': priority_counts
            }

    def get_customer_stats(self) -> Dict[str, Any]:
        """
        Get customer statistics.

        Returns:
            Dictionary with customer counts
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("""
                SELECT status, COUNT(*) as count
                FROM customers
                GROUP BY status
            """)
            status_counts = {row['status']: row['count'] for row in cursor.fetchall()}

            cursor.execute("SELECT COUNT(*) as total FROM customers")
            total = cursor.fetchone()['total']

            return {
                'total_customers': total,
                'by_status': status_counts
            }

    def search_tickets(self, keyword: str) -> List[Dict[str, Any]]:
        """
        Search tickets by keyword in issue text.

        Args:
            keyword: Search keyword

        Returns:
            List of matching tickets
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT t.*, c.name as customer_name, c.email as customer_email,
                       c.phone as customer_phone, c.status as customer_status
                FROM tickets t
                JOIN customers c ON t.customer_id = c.id
                WHERE t.issue LIKE ?
                ORDER BY t.created_at DESC
            """, (f'%{keyword}%',))
            return [dict(row) for row in cursor.fetchall()]
