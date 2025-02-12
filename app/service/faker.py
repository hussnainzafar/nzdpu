import calendar
import random
import string
from datetime import date, datetime, time

DEFAULT_MAX_NUMBER = 999


class Faker:
    """
    Faker provider class for fake submissions
    """

    # pylint: disable = redefined-builtin, unsupported-binary-operation
    def text(
        self, name: str = "text", min: int = 0, max: int | None = None
    ) -> str:
        """
        Generate a fake string of text, constrained if necessary.
        Args:
            name (str, optional): An optional descrption.
                Defaults to "text".
            min (int, optional): Minimun length. Defaults to 0.
            max (int, optional): Maximum length. Defaults to None.
        Returns:
            str: A fake string.
        """
        text = f"Fake {name} {random.randint(1, 999)}"
        # fulfill constraints
        return text.zfill(min - len(text))[:max]

    # pylint: disable = redefined-builtin
    def number(
        self,
        min: int = 0,
        max: int = DEFAULT_MAX_NUMBER,
        is_float: bool = False,
        **kwargs,
    ) -> int | float:
        """
        Generate a fake random number, constrained if necessary.
        Args:
            min (Union[int, float], optional): Minimum value (not included).
                Defaults to 0.
            max (Union[int, float], optional): Maximum value (not included).
                Defaults to DEFAULT_MAX_NUMBER.
            is_float (bool, optional): Returns float if True.
                Defaults to False.
        Returns:
            Union[int, float]: A random number.
        """
        number = random.randint(min, max)
        if is_float:
            number = round(
                float(number - 1 if number else number) + random.random(), 2
            )
        return number

    # pylint: disable = redefined-builtin
    def datetime(
        self,
        min: datetime = datetime.combine(date.min, time.min),
        max: datetime = datetime.combine(date.max, time.max),
    ):
        """
        Generates a fake random datetime, constrained if necessary.
        Args:
            min (datetime, optional): Minimum datetime constraint.
                Defaults to datetime.combine(date.min, time.min).
            max (datetime, optional): Maximum datetime constraint.
                Defaults to datetime.combine(date.max, time.max).
        Returns:
            datetime: The faked random datetime
        """
        # convert min and max constraints to epoch values
        min_epoch = calendar.timegm(min.timetuple())
        max_epoch = calendar.timegm(max.timetuple())
        # use epoch constrainst to get random epoch
        random_epoch = random.randint(min_epoch, max_epoch)
        # return random datetime from random epoch
        return datetime.fromtimestamp(random_epoch)

    def sample(self, name: str = "table") -> str:
        """
        Generate a fake sample table name.
        Args:
            name (str, optional): An optional description.
                Defaults to "table".
        Returns:
            str: A fake table name.
        """
        return f"sample_{name}_{str(random.randint(0, 999999)).zfill(6)}"

    def lei(
        self, size=20, chars=string.ascii_uppercase + string.digits
    ) -> str:
        return "".join(random.choice(chars) for _ in range(size))
