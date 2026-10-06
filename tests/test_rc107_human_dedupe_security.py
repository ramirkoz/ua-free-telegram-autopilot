from __future__ import annotations

import base64
import os
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from telegram_autopilot.v2.editorial_review import ensure_editorial_state_schema
from telegram_autopilot.v2.event_dedupe_guard import _validated_cluster_same_event
from telegram_autopilot.v2.storage import V2Store, now_iso
from telegram_autopilot.v2.update_signing import canonical_manifest_bytes, verify_manifest_signature


def _seed(store: V2Store) -> int:
    ensure_editorial_state_schema(store)
    stamp=now_iso()
    with store.connect() as con:
        con.execute("INSERT INTO channels(id,name,telegram_chat_id,created_at,updated_at) VALUES(1,'T','@t',?,?)",(stamp,stamp))
        source=int(con.execute("INSERT INTO sources(channel_id,kind,name,url) VALUES(1,'page','S','https://example.com')").lastrowid)
        aid=int(con.execute(
            """INSERT INTO articles(channel_id,source_id,external_id,title,source_url,canonical_source_url,raw_text,
               discovered_at,stage,decision,blocked_by,final_text,ready_at,last_error_code,last_error_detail)
               VALUES(1,?,'a','A','https://example.com/a','https://example.com/a','body',?,
                      'ARCHIVED','REJECT','NONE','approved text',?,'STALE_READY_MAX_AGE','expired')""",
            (source,stamp,stamp),
        ).lastrowid)
        con.execute(
            "INSERT INTO editorial_actions(article_id,channel_id,action,title,before_text,after_text,detail,created_at) VALUES(1,1,'approve','A','approved text','approved text','',?)",
            (stamp,),
        )
    return aid


def test_rc107_reconciles_operator_owned_approval(tmp_path: Path) -> None:
    store=V2Store(tmp_path/"rc107.sqlite3")
    aid=_seed(store)
    result=store.reconcile_human_approved_unpublished()
    row=store.get_article(aid)
    assert result["restored"] == 1
    assert row is not None
    assert str(row["stage"]) == "READY"
    assert str(row["decision"]) == "PUBLISH"
    summary=store.human_approved_summary(1)
    assert summary["total_unpublished"] == 1
    assert summary["ready"] == 1


def test_rc107_validated_cluster_activation_is_conservative() -> None:
    stats={
        "containment":0.74,
        "salient_containment":0.72,
        "salient_shared":{"alpha","bravo","charlie","delta","echo","foxtrot","golf"},
        "shared_entities":{"Citrix","NetScaler"},
        "shared_actions":{"hack"},
        "shared_scientific":set(),
        "shared_rare":{"gateway","saml"},
        "quantity_pairs":[],
        "duration_pairs":[],
        "numeric_pairs":[(1.0,1.0)],
    }
    same, reason=_validated_cluster_same_event(stats)
    assert same is True
    assert "RC107 validated cluster duplicate" in reason

    weak=dict(stats)
    weak["shared_entities"]=set()
    weak["shared_actions"]=set()
    same2,_=_validated_cluster_same_event(weak)
    assert same2 is False


def test_rc107_signed_manifest_verification(monkeypatch) -> None:
    private=Ed25519PrivateKey.generate()
    public=private.public_key()
    pem=public.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode("utf-8")
    monkeypatch.setenv("UA_FREE_AUTOPILOT_UPDATE_PUBLIC_KEY_PEM",pem)
    manifest={
        "schema":"ua-free-autopilot-update-v1",
        "version":"2.0.0-rc107",
        "artifact_filename":"UA_FREE_Telegram_Autopilot_v2.0.0-rc107_Update.zip",
        "sha256":"a"*64,
        "source_commit":"deadbeef",
        "created_at":"2026-10-06T00:00:00Z",
        "request_id":"release-2-0-0-rc107",
        "approved_for_auto_update":True,
        "ci_passed":True,
        "windows_build_passed":True,
    }
    manifest["signature_algorithm"]="ed25519"
    manifest["key_id"]="test"
    manifest["signature_b64"]=base64.b64encode(private.sign(canonical_manifest_bytes(manifest))).decode("ascii")
    assert verify_manifest_signature(manifest) is True
    manifest["sha256"]="b"*64
    assert verify_manifest_signature(manifest) is False
