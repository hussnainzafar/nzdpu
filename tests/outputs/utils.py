from enum import Enum

import pandas as pd

from app.db.models import Organization
from tests.routers.utils import NZ_ID


class GleifMeta(str, Enum):
    """
    GLEIF format
    """

    F_LEI = "LEI"
    F_LEGAL_NAME = "Entity.LegalName"
    F_JURISDICTION = "Entity.LegalJurisdiction"

    F_HEADQUARTER_ADDRESS_LINES = "Entity.HeadquartersAddress.FirstAddressLine"
    F_HEADQUARTER_ADDRESS_NUMBER = "Entity.HeadquartersAddress.AddressNumber"
    F_HEADQUARTER_CITY = "Entity.HeadquartersAddress.City"
    F_HEADQUARTER_COUNTRY = "Entity.HeadquartersAddress.Country"
    F_HEADQUARTER_LANGUAGE = "Entity.HeadquartersAddress.xmllang"
    F_HEADQUARTER_POSTAL_CODE = "Entity.HeadquartersAddress.PostalCode"
    F_HEADQUARTER_REGION = "Entity.HeadquartersAddress.Region"

    F_LEGAL_ADDRESS_LINES = "Entity.LegalAddress.FirstAddressLine"
    F_LEGAL_ADDRESS_NUMBER = "Entity.LegalAddress.AddressNumber"
    F_LEGAL_CITY = "Entity.LegalAddress.City"
    F_LEGAL_COUNTRY = "Entity.LegalAddress.Country"
    F_LEGAL_LANGUAGE = "Entity.LegalAddress.xmllang"
    F_LEGAL_POSTAL_CODE = "Entity.LegalAddress.PostalCode"
    F_LEGAL_REGION = "Entity.LegalAddress.Region"


def create_entities(df_src: pd.DataFrame) -> list[Organization]:
    """
    Creates a new list of ORM entities
    Parameters
    ----------
    leis: list of LEI identifiers to assign to the entities we want to create
    df_src: dataframe to get entity data from
    Returns
    -------
    list of new entities
    """

    entities: list[Organization] = []

    for index, entity_data in df_src.iterrows():
        entity = Organization(
            nz_id=NZ_ID + index + 1,
            lei=(
                entity_data[GleifMeta.F_LEI]
                if pd.notna(entity_data[GleifMeta.F_LEI])
                else None
            ),
            legal_name=(
                entity_data[GleifMeta.F_LEGAL_NAME]
                if pd.notna(entity_data[GleifMeta.F_LEGAL_NAME])
                else None
            ),
            jurisdiction=(
                entity_data[GleifMeta.F_JURISDICTION]
                if pd.notna(entity_data[GleifMeta.F_JURISDICTION])
                else None
            ),
            headquarter_address_lines=(
                entity_data[GleifMeta.F_HEADQUARTER_ADDRESS_LINES]
                if pd.notna(entity_data[GleifMeta.F_HEADQUARTER_ADDRESS_LINES])
                else None
            ),
            headquarter_city=(
                entity_data[GleifMeta.F_HEADQUARTER_CITY]
                if pd.notna(entity_data[GleifMeta.F_HEADQUARTER_CITY])
                else None
            ),
            headquarter_country=(
                entity_data[GleifMeta.F_HEADQUARTER_COUNTRY]
                if pd.notna(entity_data[GleifMeta.F_HEADQUARTER_COUNTRY])
                else None
            ),
            headquarter_language=(
                entity_data[GleifMeta.F_HEADQUARTER_LANGUAGE]
                if pd.notna(entity_data[GleifMeta.F_HEADQUARTER_LANGUAGE])
                else None
            ),
            headquarter_postal_code=(
                entity_data[GleifMeta.F_HEADQUARTER_POSTAL_CODE]
                if pd.notna(entity_data[GleifMeta.F_HEADQUARTER_POSTAL_CODE])
                else None
            ),
            headquarter_region=(
                entity_data[GleifMeta.F_HEADQUARTER_REGION]
                if pd.notna(entity_data[GleifMeta.F_HEADQUARTER_REGION])
                else None
            ),
            legal_address_lines=(
                entity_data[GleifMeta.F_LEGAL_ADDRESS_LINES]
                if pd.notna(entity_data[GleifMeta.F_LEGAL_ADDRESS_LINES])
                else None
            ),
            legal_city=(
                entity_data[GleifMeta.F_LEGAL_CITY]
                if pd.notna(entity_data[GleifMeta.F_LEGAL_CITY])
                else None
            ),
            legal_country=(
                entity_data[GleifMeta.F_LEGAL_COUNTRY]
                if pd.notna(entity_data[GleifMeta.F_LEGAL_COUNTRY])
                else None
            ),
            legal_language=(
                entity_data[GleifMeta.F_LEGAL_LANGUAGE]
                if pd.notna(entity_data[GleifMeta.F_LEGAL_LANGUAGE])
                else None
            ),
            legal_postal_code=(
                entity_data[GleifMeta.F_LEGAL_POSTAL_CODE]
                if pd.notna(entity_data[GleifMeta.F_LEGAL_POSTAL_CODE])
                else None
            ),
            legal_region=(
                entity_data[GleifMeta.F_LEGAL_REGION]
                if pd.notna(entity_data[GleifMeta.F_LEGAL_REGION])
                else None
            ),
            legal_address_number=(
                entity_data[GleifMeta.F_LEGAL_ADDRESS_NUMBER]
                if pd.notna(entity_data[GleifMeta.F_LEGAL_ADDRESS_NUMBER])
                else None
            ),
            headquarter_address_number=(
                entity_data[GleifMeta.F_HEADQUARTER_ADDRESS_NUMBER]
                if pd.notna(
                    entity_data[GleifMeta.F_HEADQUARTER_ADDRESS_NUMBER]
                )
                else None
            ),
        )
        if pd.notna(entity_data[GleifMeta.F_LEGAL_NAME]):
            entities.append(entity)

    return entities
