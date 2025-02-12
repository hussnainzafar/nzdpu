def get_order_by(string: str):
    if string.lower() == "asc":
        return "ASC"
    if string.lower() == "desc":
        return "DESC"
    return ""
