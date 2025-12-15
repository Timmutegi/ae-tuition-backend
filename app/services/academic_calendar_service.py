"""
Academic Calendar Service

Manages the 40-week UK academic calendar for AE Tuition.
- Academic year starts: September 5, 2025 (Friday)
- Week cycle: Friday to Wednesday (7 days)
- 40 weeks total with configurable breaks
"""

from datetime import datetime, date, timedelta
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass


@dataclass
class BreakPeriod:
    """Represents a break period in the academic calendar."""
    name: str
    start_date: date
    end_date: date


@dataclass
class AcademicWeekInfo:
    """Information about an academic week."""
    week_number: int
    start_date: date
    end_date: date
    is_break: bool
    break_name: Optional[str] = None


class AcademicCalendarService:
    """
    Service for managing the academic calendar and week calculations.

    The UK academic year for AE Tuition:
    - Starts: Friday, September 5, 2025
    - Week cycle: Friday - Wednesday (7 days)
    - Total: 40 weeks
    - Breaks: Christmas, Easter, Summer (configurable)
    """

    # Academic year start date (Friday, September 5, 2025)
    ACADEMIC_YEAR_START = date(2025, 9, 5)

    # Total number of weeks in academic year
    TOTAL_WEEKS = 40

    # Default break periods (configurable)
    DEFAULT_BREAKS = [
        BreakPeriod(
            name="Christmas Break",
            start_date=date(2025, 12, 12),
            end_date=date(2026, 1, 2)
        ),
        BreakPeriod(
            name="Easter Break",
            start_date=date(2026, 4, 10),
            end_date=date(2026, 4, 24)
        ),
        BreakPeriod(
            name="Summer Break",
            start_date=date(2026, 7, 3),
            end_date=date(2026, 7, 24)
        )
    ]

    def __init__(self, breaks: Optional[List[BreakPeriod]] = None):
        """
        Initialize the academic calendar service.

        Args:
            breaks: List of break periods. Uses DEFAULT_BREAKS if not provided.
        """
        self.breaks = breaks if breaks is not None else self.DEFAULT_BREAKS

    def get_current_week(self, reference_date: Optional[date] = None) -> int:
        """
        Get the current academic week number.

        Args:
            reference_date: Date to calculate week for. Uses today if not provided.

        Returns:
            Week number (1-40), or 0 if before academic year starts or after it ends.
        """
        if reference_date is None:
            reference_date = date.today()

        # If before academic year starts
        if reference_date < self.ACADEMIC_YEAR_START:
            return 0

        # Calculate days since start
        days_since_start = (reference_date - self.ACADEMIC_YEAR_START).days

        # Calculate week number (Friday to Wednesday = 7 days)
        week_number = (days_since_start // 7) + 1

        # Cap at 40 weeks
        if week_number > self.TOTAL_WEEKS:
            return 0

        return week_number

    def get_week_info(self, week_number: int) -> AcademicWeekInfo:
        """
        Get detailed information about a specific academic week.

        Args:
            week_number: Week number (1-40)

        Returns:
            AcademicWeekInfo object with week details

        Raises:
            ValueError: If week_number is out of range
        """
        if week_number < 1 or week_number > self.TOTAL_WEEKS:
            raise ValueError(f"Week number must be between 1 and {self.TOTAL_WEEKS}")

        # Calculate start date (Friday)
        days_offset = (week_number - 1) * 7
        start_date = self.ACADEMIC_YEAR_START + timedelta(days=days_offset)

        # Calculate end date (Wednesday, 6 days after Friday)
        end_date = start_date + timedelta(days=6)

        # Check if week falls within a break
        is_break, break_name = self._is_date_in_break(start_date)

        return AcademicWeekInfo(
            week_number=week_number,
            start_date=start_date,
            end_date=end_date,
            is_break=is_break,
            break_name=break_name
        )

    def get_week_date_range(self, week_number: int) -> Tuple[date, date]:
        """
        Get the start and end dates for a specific week.

        Args:
            week_number: Week number (1-40)

        Returns:
            Tuple of (start_date, end_date)
        """
        week_info = self.get_week_info(week_number)
        return (week_info.start_date, week_info.end_date)

    def date_to_week_number(self, target_date: date) -> int:
        """
        Convert a date to its academic week number.

        Args:
            target_date: Date to convert

        Returns:
            Week number (1-40), or 0 if outside academic year
        """
        return self.get_current_week(target_date)

    def get_all_weeks_info(self) -> List[AcademicWeekInfo]:
        """
        Get information for all 40 academic weeks.

        Returns:
            List of AcademicWeekInfo objects for all weeks
        """
        return [self.get_week_info(week_num) for week_num in range(1, self.TOTAL_WEEKS + 1)]

    def get_week_label(self, week_number: int) -> str:
        """
        Get the display label for a week.

        Args:
            week_number: Week number (1-40)

        Returns:
            Formatted week label (e.g., "Week1", "Week2")
        """
        if week_number < 1 or week_number > self.TOTAL_WEEKS:
            return "Invalid Week"
        return f"Week{week_number}"

    def format_week_date_range(self, week_number: int, format_str: str = "%b %d, %Y") -> str:
        """
        Format a week's date range as a string.

        Args:
            week_number: Week number (1-40)
            format_str: Date format string

        Returns:
            Formatted date range string (e.g., "Sep 05, 2025 - Sep 11, 2025")
        """
        week_info = self.get_week_info(week_number)
        start_str = week_info.start_date.strftime(format_str)
        end_str = week_info.end_date.strftime(format_str)
        return f"{start_str} - {end_str}"

    def _is_date_in_break(self, check_date: date) -> Tuple[bool, Optional[str]]:
        """
        Check if a date falls within a break period.

        Args:
            check_date: Date to check

        Returns:
            Tuple of (is_break, break_name)
        """
        for break_period in self.breaks:
            if break_period.start_date <= check_date <= break_period.end_date:
                return (True, break_period.name)
        return (False, None)

    def get_weeks_in_date_range(self, start_date: date, end_date: date) -> List[int]:
        """
        Get all academic week numbers that fall within a date range.

        Args:
            start_date: Start of date range
            end_date: End of date range

        Returns:
            List of week numbers
        """
        weeks = []
        current_date = start_date

        while current_date <= end_date:
            week_num = self.date_to_week_number(current_date)
            if week_num > 0 and week_num not in weeks:
                weeks.append(week_num)
            current_date += timedelta(days=1)

        return sorted(weeks)

    def get_break_weeks(self) -> Dict[str, List[int]]:
        """
        Get week numbers that fall during break periods.

        Returns:
            Dictionary mapping break names to lists of week numbers
        """
        break_weeks = {}

        for break_period in self.breaks:
            weeks = self.get_weeks_in_date_range(
                break_period.start_date,
                break_period.end_date
            )
            break_weeks[break_period.name] = weeks

        return break_weeks

    def is_week_in_break(self, week_number: int) -> Tuple[bool, Optional[str]]:
        """
        Check if a specific week is during a break period.

        Args:
            week_number: Week number to check

        Returns:
            Tuple of (is_break, break_name)
        """
        week_info = self.get_week_info(week_number)
        return (week_info.is_break, week_info.break_name)

    @staticmethod
    def get_academic_year_string() -> str:
        """
        Get the academic year as a string (e.g., "2025-2026").

        Returns:
            Academic year string
        """
        start_year = AcademicCalendarService.ACADEMIC_YEAR_START.year
        return f"{start_year}-{start_year + 1}"

    def get_academic_year_dates(self) -> Tuple[date, date]:
        """
        Get the start and end dates for the academic year.

        Returns:
            Tuple of (start_date, end_date) for the academic year
        """
        start_date = self.ACADEMIC_YEAR_START
        # End date is the last day of week 40 (Wednesday)
        # Week 40 starts at (40-1)*7 = 273 days from start
        # End of week 40 is 273 + 6 = 279 days from start
        end_date = start_date + timedelta(days=(self.TOTAL_WEEKS - 1) * 7 + 6)
        return (start_date, end_date)


# Create singleton instance
calendar_service = AcademicCalendarService()
