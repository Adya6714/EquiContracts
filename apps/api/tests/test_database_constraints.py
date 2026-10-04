from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from apps.api.app.core.db import AdminSessionFactory


def test_financial_field_cannot_verify_without_human(access_data) -> None:
    session = AdminSessionFactory()
    try:
        with pytest.raises(IntegrityError):
            session.execute(
                text(
                    """
                    INSERT INTO extracted_field (
                      document_id, field_name, field_value, state,
                      is_financial, verified_at
                    )
                    VALUES (
                      :document_id, 'bg_value', '17080000.00',
                      'verified', true, now()
                    )
                    """
                ),
                {"document_id": access_data.document_a},
            )
            session.flush()
    finally:
        session.rollback()
        session.close()


def test_bg_dual_dates_accept_real_values_and_reject_inverted(access_data) -> None:
    session = AdminSessionFactory()
    work_order_id = uuid4()
    valid_bg_id = uuid4()
    try:
        session.execute(
            text(
                """
                INSERT INTO work_order (id, engagement_id, wo_number)
                VALUES (:id, :engagement_id, :number)
                """
            ),
            {
                "id": work_order_id,
                "engagement_id": access_data.project_a,
                "number": f"WO-{uuid4().hex}",
            },
        )
        session.execute(
            text(
                """
                INSERT INTO bank_guarantee (
                  id, work_order_id, bg_number, bg_type, value,
                  expiry_date, claim_expiry_date
                )
                VALUES (
                  :id, :work_order_id, '0544BGR0097618', 'performance',
                  :value, DATE '2023-04-23', DATE '2024-04-23'
                )
                """
            ),
            {
                "id": valid_bg_id,
                "work_order_id": work_order_id,
                "value": Decimal("17080000.00"),
            },
        )
        session.flush()
        with pytest.raises(IntegrityError):
            session.execute(
                text(
                    """
                    INSERT INTO bank_guarantee (
                      work_order_id, bg_number, bg_type, value,
                      expiry_date, claim_expiry_date
                    )
                    VALUES (
                      :work_order_id, 'INVERTED', 'performance', :value,
                      DATE '2024-04-23', DATE '2023-04-23'
                    )
                    """
                ),
                {
                    "work_order_id": work_order_id,
                    "value": Decimal("1.00"),
                },
            )
            session.flush()
    finally:
        session.rollback()
        session.close()
