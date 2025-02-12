from sqlalchemy import inspect


def object_as_dict(obj):
    """
    Return a dictionary from an object

    Parameters
    ----------
    obj - source object

    Returns
    -------
    object dictionary

    """
    return {
        c.key: getattr(obj, c.key) for c in inspect(obj).mapper.column_attrs
    }
