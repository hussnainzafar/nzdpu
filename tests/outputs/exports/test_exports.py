"""
Unit tests for exports methods
"""

import json
from pathlib import Path

import pandas as pd
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from app import settings
from app.routers.utils import load_organization
from app.service.core.cache import CoreMemoryCache
from app.service.exports.companies_download import CompaniesExportManager
from app.service.exports.forms_processor import (
    process_company_metadata,
    process_data_export,
    process_scope_emissions,
)
from app.service.exports.headers.headers import ExportOptions
from app.service.exports.utils import (
    format_datetime_for_downloads,
    scope_emissions_formatter,
)
from app.service.utils import parse_and_transform_subscripts_to_normal
from tests.constants import SCHEMA_FILE_NAME, SUBMISSION_SCHEMA_FULL_FILE_NAME
from tests.outputs.utils import create_entities
from tests.routers.auth_test import AuthTest
from tests.routers.utils import NZ_ID, create_test_form

BASE_ENDPOINT = "/coverage/companies"
data_dir: Path = settings.BASE_DIR.parent / "tests" / "data"


@pytest.fixture
def submission_payload():
    """
    Fixture for submission payload
    Returns
    -------
    submissions payload
    """

    with open(data_dir / SUBMISSION_SCHEMA_FULL_FILE_NAME) as f:
        return {
            "nz_id": NZ_ID,
            "table_view_id": 1,
            "permissions_set_id": 1,
            "values": json.load(f),
        }


class TestCompaniesExport(AuthTest):
    @staticmethod
    async def insert_organization(session: AsyncSession):
        try:
            df = pd.read_csv("tests/outputs/companies/data/organizations.csv")
            entities = create_entities(df)
            session.add_all(entities)
            # commit the transaction
            await session.commit()

        except Exception as e:
            print(f"Error during insertion: {e}")
            # Rollback the transaction in case of an error
            await session.rollback()
        finally:
            # Close the session
            await session.close()

    @pytest.mark.asyncio
    async def insert_submission_and_get_companies_history_response(
        self, session: AsyncSession, client: AsyncClient, submission_payload
    ):
        # act
        response = await client.post(
            url="/submissions",
            json=submission_payload,
            headers={
                "content-type": "application/json",
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )
        # assert
        assert response.status_code == status.HTTP_200_OK, response.text
        # act
        response = await client.get(
            url=f"{BASE_ENDPOINT}/{NZ_ID}/history",
            headers={
                "content-type": "application/json",
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )
        organization = await load_organization(
            organization_id=1, session=session
        )
        res_history = response.json().get("history")[0]
        reporting_year = res_history.get("reporting_year")
        res_history_values = res_history.get("submission").get("values")
        return organization, reporting_year, res_history, res_history_values

    @pytest.mark.asyncio
    async def test_metadata_form_processor(
        self,
        client: AsyncClient,
        session: AsyncSession,
        static_cache: CoreMemoryCache,
        submission_payload,
    ):
        """
        Test historical emissions download for metadata form processor method.
        """

        # arrange
        await create_test_form(data_dir / SCHEMA_FILE_NAME, session)
        # create test permissions
        await self.create_test_permissions(session)
        # add admin permission to user
        await self.add_admin_permissions_to_user(session)
        await self.insert_organization(session)
        await static_cache.refresh_values()

        (
            organization,
            reporting_year,
            history,
            results,
        ) = await self.insert_submission_and_get_companies_history_response(
            session=session,
            client=client,
            submission_payload=submission_payload,
        )
        items, description = await process_company_metadata(
            d=results,
            company=organization,
            reporting_year=reporting_year,
            session=session,
            static_cache=static_cache,
        )
        # Expected keys for items and description
        expected_keys = {
            "legal_entity_identifier",
            "legal_name",
            "jurisdiction",
            "sics_sector",
            "sics_sub_sector",
            "sics_industry",
            "data_model",
            "reporting_year",
            "date_start_reporting_year",
            "date_end_reporting_year",
            "org_boundary_approach",
        }
        assert expected_keys == set(
            items.keys()
        ), f"Missing keys in items: {expected_keys - set(items.keys())}"
        assert (
            expected_keys == set(description.keys())
        ), f"Missing keys in description: {expected_keys - set(description.keys())}"

    @pytest.mark.asyncio
    async def test_scope_emissions_form_processor(
        self,
        client: AsyncClient,
        session: AsyncSession,
        static_cache: CoreMemoryCache,
        submission_payload,
    ):
        """
        Test historical emissions download for process_scope_emissions.
        """

        # arrange
        await create_test_form(data_dir / SCHEMA_FILE_NAME, session)
        # create test permissions
        await self.create_test_permissions(session)
        # add admin permission to user
        await self.add_admin_permissions_to_user(session)
        await self.insert_organization(session)
        await static_cache.refresh_values()

        (
            organization,
            reporting_year,
            history,
            results,
        ) = await self.insert_submission_and_get_companies_history_response(
            session=session,
            client=client,
            submission_payload=submission_payload,
        )
        source = results["disclosure_source"]
        last_updated = format_datetime_for_downloads(
            results.get("reporting_datetime")
        )
        scope_1_emissions_fields = scope_emissions_formatter(
            results, "s1_emissions"
        )
        restated_fields = parse_and_transform_subscripts_to_normal(
            history.get("submission").get("restated_fields_data_source")
        )
        res_units = parse_and_transform_subscripts_to_normal(
            history.get("submission").get("units")
        )
        (
            scope_emissions_data,
            scope_emissions_desc,
            scope_emissions_source,
            scope_emissions_reported,
            scope_emissions_units,
        ) = await CompaniesExportManager._handle_process_methods(
            process_scope_emissions,
            d=results,
            source=source,
            last_updated=last_updated,
            emissions=scope_1_emissions_fields,
            session=session,
            download_option=ExportOptions.COMPANIES.value,
            static_cache=static_cache,
            restated=restated_fields,
            units=res_units,
        )
        data = {
            "total_s1_emissions_ghg": "864169.1944126465",
            "total_s1_emissions_co2": "864169.1944126465",
            "rationale_s1_emissions_non_disclose": "Vehicle Emissions",
            "s1_emissions_method": "Vehicle Emissions",
            "disclose_s1_emissions_exclusion": "Vehicle Emissions",
        }
        desc = {
            "total_s1_emissions_ghg": "Total Scope 1 GHG emissions",
            "total_s1_emissions_co2": "Total Scope 1 CO\u2082 emissions",
            "rationale_s1_emissions_non_disclose": "Rationale if Scope 1 GHG emissions not disclosed",
            "s1_emissions_method": "Methodology used to calculate Scope 1 GHG emissions",
            "disclose_s1_emissions_exclusion": "Scope 1 GHG emissions sources excluded from inventory",
        }
        source = {
            "total_s1_emissions_ghg": "Vehicle Emissions",
            "total_s1_emissions_co2": "Vehicle Emissions",
            "rationale_s1_emissions_non_disclose": "Vehicle Emissions",
            "s1_emissions_method": "Vehicle Emissions",
            "disclose_s1_emissions_exclusion": "Vehicle Emissions",
        }
        reported = {
            "total_s1_emissions_ghg": "2024-09-12",
            "total_s1_emissions_co2": "2024-09-12",
            "rationale_s1_emissions_non_disclose": "2024-09-12",
            "s1_emissions_method": "2024-09-12",
            "disclose_s1_emissions_exclusion": "2024-09-12",
        }
        assert scope_emissions_data == data
        assert scope_emissions_desc == desc
        assert scope_emissions_source == source
        assert scope_emissions_reported == reported

    @pytest.mark.asyncio
    async def test_scope_emissions_dict_form_processor(
        self,
        client: AsyncClient,
        session: AsyncSession,
        static_cache: CoreMemoryCache,
        submission_payload,
    ):
        """
        Test historical emissions download for process_data_export.
        """

        # arrange
        await create_test_form(data_dir / SCHEMA_FILE_NAME, session)
        # create test permissions
        await self.create_test_permissions(session)
        # add admin permission to user
        await self.add_admin_permissions_to_user(session)
        await self.insert_organization(session)
        await static_cache.refresh_values()

        (
            organization,
            reporting_year,
            history,
            results,
        ) = await self.insert_submission_and_get_companies_history_response(
            session=session,
            client=client,
            submission_payload=submission_payload,
        )
        source = results["disclosure_source"]
        last_updated = format_datetime_for_downloads(
            results.get("reporting_datetime")
        )
        restated_fields = parse_and_transform_subscripts_to_normal(
            history.get("submission").get("restated_fields_data_source")
        )
        res_units = parse_and_transform_subscripts_to_normal(
            history.get("submission").get("units")
        )

        units_list = res_units.get("s1_emissions_exclusion_dict") or []

        (
            scope_exclusion_data,
            scope_exclusion_desc,
            scope_exclusion_source,
            scope_exclusion_reported,
            scope_emissions_units,
        ) = await CompaniesExportManager._handle_process_methods(
            process_data_export,
            data_export_list=results.get("s1_emissions_exclusion_dict"),
            source=source,
            last_updated=last_updated,
            form_name="s1_emissions_exclusion_dict",
            session=session,
            download_option=ExportOptions.COMPANIES.value,
            static_cache=static_cache,
            restated=restated_fields,
            units_list=units_list,
        )
        data = {
            "s1_emissions_exclusion_desc_1": "Vehicle Emissions",
            "s1_emissions_exclusion_explan_1": "Vehicle Emissions",
            "s1_emissions_exclusion_perc_1": "864169.1944126465",
            "s1_emissions_exclusion_perc_explan_1": "Vehicle Emissions",
            "s1_emissions_exclusion_desc_2": "Vehicle Emissions",
            "s1_emissions_exclusion_explan_2": "Vehicle Emissions",
            "s1_emissions_exclusion_perc_2": "864169.1944126465",
            "s1_emissions_exclusion_perc_explan_2": "Vehicle Emissions",
        }
        desc = {
            "s1_emissions_exclusion_desc_1": "Description of Scope 1 GHG emissions source excluded from inventory (1)",
            "s1_emissions_exclusion_explan_1": "Explanation of why Scope 1 GHG emissions source is excluded from inventory (1)",
            "s1_emissions_exclusion_perc_1": "Estimated percentage of Scope 1 GHG emissions excluded from inventory (1)",
            "s1_emissions_exclusion_perc_explan_1": "Explanation of how percentage of Scope 1 GHG emissions excluded was calculated (1)",
            "s1_emissions_exclusion_desc_2": "Description of Scope 1 GHG emissions source excluded from inventory (2)",
            "s1_emissions_exclusion_explan_2": "Explanation of why Scope 1 GHG emissions source is excluded from inventory (2)",
            "s1_emissions_exclusion_perc_2": "Estimated percentage of Scope 1 GHG emissions excluded from inventory (2)",
            "s1_emissions_exclusion_perc_explan_2": "Explanation of how percentage of Scope 1 GHG emissions excluded was calculated (2)",
        }
        source = {
            "s1_emissions_exclusion_desc_1": "Vehicle Emissions",
            "s1_emissions_exclusion_explan_1": "Vehicle Emissions",
            "s1_emissions_exclusion_perc_1": "Vehicle Emissions",
            "s1_emissions_exclusion_perc_explan_1": "Vehicle Emissions",
            "s1_emissions_exclusion_desc_2": "Vehicle Emissions",
            "s1_emissions_exclusion_explan_2": "Vehicle Emissions",
            "s1_emissions_exclusion_perc_2": "Vehicle Emissions",
            "s1_emissions_exclusion_perc_explan_2": "Vehicle Emissions",
        }
        reported = {
            "s1_emissions_exclusion_desc_1": "2024-09-12",
            "s1_emissions_exclusion_explan_1": "2024-09-12",
            "s1_emissions_exclusion_perc_1": "2024-09-12",
            "s1_emissions_exclusion_perc_explan_1": "2024-09-12",
            "s1_emissions_exclusion_desc_2": "2024-09-12",
            "s1_emissions_exclusion_explan_2": "2024-09-12",
            "s1_emissions_exclusion_perc_2": "2024-09-12",
            "s1_emissions_exclusion_perc_explan_2": "2024-09-12",
        }
        units = {
            "s1_emissions_exclusion_desc_1": None,
            "s1_emissions_exclusion_explan_1": None,
            "s1_emissions_exclusion_perc_1": "",
            "s1_emissions_exclusion_perc_explan_1": None,
            "s1_emissions_exclusion_desc_2": None,
            "s1_emissions_exclusion_explan_2": None,
            "s1_emissions_exclusion_perc_2": "",
            "s1_emissions_exclusion_perc_explan_2": None,
        }
        assert scope_exclusion_data == data
        assert scope_exclusion_desc == desc
        assert scope_exclusion_source == source
        assert scope_exclusion_reported == reported
        assert scope_emissions_units == units
