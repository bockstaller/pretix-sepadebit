import pytest
from datetime import timedelta
from django.core.exceptions import ObjectDoesNotExist
from django.utils.timezone import now
from django_scopes import scopes_disabled
from pretix.base.models import (
    Event, Item, Order, OrderPayment, Organizer, Quota,
)
import importlib



from pretix_sepadebit.models import SepaDueDate
from pretix_sepadebit.payment import SepaDebit

migration =  importlib.import_module('pretix_sepadebit.migrations.0007_sepaduedate')

@pytest.fixture
def event():
    # IBAN and BIC are random  values
    o = Organizer.objects.create(name='Dummy', slug='dummy')
    event = Event.objects.create(
        organizer=o, name='Dummy', slug='dummy',
        date_from=now(), plugins='pretix.plugins.sepadebit'
    )
    event.settings.set('payment_sepadebit_creditor_name', '1.00')
    event.settings.set('payment_sepadebit_creditor_iban', 'DE13495179316396679327')
    event.settings.set('payment_sepadebit_creditor_bic', 'THISISNOBIC')
    # testing creditor id from https://www.bundesbank.de/en/tasks/payment-systems/services/sepa/creditor-identifier/creditor-identifier-626704
    event.settings.set('payment_sepadebit_creditor_id', 'DE98ZZZ09999999999')

    quota = Quota.objects.create(name="Test", size=2, event=event)
    item1 = Item.objects.create(event=event, name="Ticket", default_price=23)
    quota.items.add(item1)
    # OrderPosition.objects.create(order=o1, item=item1, variation=None, price=23)
    return event


@pytest.fixture
def order(event):
    with scopes_disabled():
        o = Order.objects.create(
            event=event,
            status=Order.STATUS_PENDING,
            datetime=now(), expires=now().date() + timedelta(days=10),
            total=23,
        )
        o.save()
        return o


@pytest.mark.parametrize(
    "earliest_due_date,prenotification_days,order_date,due_date",
    [
        # Testing the transition from earliest_due_date to prenotification based _due_date computation
        (now() + timedelta(days=14), 7, now() - timedelta(days=123), now().date() + timedelta(days=14)),
        (now() + timedelta(days=14), 7, now(), now().date() + timedelta(days=14)),
        (now() + timedelta(days=14), 7, now() + timedelta(days=6), now().date() + timedelta(days=14)),
        (now() + timedelta(days=14), 7, now() + timedelta(days=7), now().date() + timedelta(days=14)),
        (now() + timedelta(days=14), 7, now() + timedelta(days=8), now().date() + timedelta(days=15)),
        (now() + timedelta(days=14), 7, now() + timedelta(days=9), now().date() + timedelta(days=16)),
        # Only prenotification based _due_date computation
        (None, 7, now() - timedelta(days=123), now().date() + timedelta(days=7) - timedelta(days=123)),
        (None, 7, now(), now().date() + timedelta(days=7)),
        (None, 7, now() + timedelta(days=1), now().date() + timedelta(days=7) + timedelta(days=1)),
        (None, 7, now() + timedelta(days=2), now().date() + timedelta(days=7) + timedelta(days=2)),
        (None, 7, now() + timedelta(days=3), now().date() + timedelta(days=7) + timedelta(days=3)),
        (None, 7, now() + timedelta(days=4), now().date() + timedelta(days=7) + timedelta(days=4))
    ]
)
@pytest.mark.django_db
def test_due_date_with_earliest_due_date(event, earliest_due_date, prenotification_days, order_date, due_date):
    if earliest_due_date:
        event.settings.set('payment_sepadebit_earliest_due_date', earliest_due_date)
    event.settings.set('payment_sepadebit_prenotification_days', prenotification_days)
    sepa = SepaDebit(event)

    o = Order.objects.create(
        code='123AB', event=event,
        status=Order.STATUS_PENDING,
        datetime=order_date, expires=order_date + timedelta(days=10),
        total=23,
    )

    assert due_date == sepa._due_date(o)


def orderpayment(order, date, remind_after, reminded=None, old_format=True):
    op_date = date
    op = OrderPayment(order=order, amount=11, provider='sepadebit')
    info_data = {'Testdata': 'is not deleted'}

    if old_format:
        info_data['date'] = op_date.strftime("%Y-%m-%d")
        info_data['remind_after'] = remind_after.strftime("%Y-%m-%d-%H-%M-%S")
        info_data['reminded'] =reminded
        op.info_data = info_data
        op.save()
    else:
        op.info_data = info_data
        op.save()
        due_date = SepaDueDate(date=op_date, reminded=reminded, remind_after=remind_after)
        due_date.payment = op
        due_date.save()
    return op


@pytest.mark.django_db
def test_create_sepaduedate_instances(event, order):
    with scopes_disabled():
        op_date = now().date()
        remind_after=op_date+timedelta(days=1)
        op = orderpayment(order, op_date, remind_after=remind_after)

        migration.create_sepaduedate_instances(OrderPayment, SepaDueDate)

        op.refresh_from_db()

        assert op.due.date == op_date
        with pytest.raises(KeyError):
            op.info_data['date']
        assert op.info_data['Testdata'] == 'is not deleted'
        assert op.due.reminded == True
        assert op.due.remind_after.date() == op.due.date


@pytest.mark.django_db
def test_create_sepaduedate_no_instances(event):
    with scopes_disabled():
        try:
            migration.create_sepaduedate_instances(OrderPayment, SepaDueDate)
        except Exception:
            pytest.fail("Shouldn't raise exception if no matching OrderPayment exists.")


@pytest.mark.django_db
def test_delete_sepaduedate_instances(event, order):
    with scopes_disabled():
        op_date = now().date()
        remind_after=op_date+timedelta(days=1)
        op = orderpayment(order, date=op_date, reminded=True, remind_after=remind_after, old_format=False)

        migration.delete_sepaduedate_instances(OrderPayment, SepaDueDate)

        op.refresh_from_db()

        with pytest.raises(ObjectDoesNotExist):
            op.due
        assert op.info_data['date'] == op_date.strftime("%Y-%m-%d")
        assert op.info_data['Testdata'] == 'is not deleted'
        assert op.info_data['reminded'] == True
        assert op.info_data['remind_after'] == remind_after.strftime("%Y-%m-%d-%H-%M-%S")


@pytest.mark.django_db
def test_delete_sepaduedate_no_instances(event):
    with scopes_disabled():
        try:
            migration.delete_sepaduedate_instances(OrderPayment, SepaDueDate)
        except Exception:
            pytest.fail("Shouldn't raise exception if no matching OrderPayment exists.")
