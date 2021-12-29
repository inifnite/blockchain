import asyncio
import json
import time

from indy import pool, wallet, did, ledger, anoncreds, blob_storage
from indy.error import ErrorCode, IndyError
from indy.pairwise import get_pairwise

from os.path import dirname


async def verifier_get_entities_from_ledger(pool_handle, _did, identifiers, actor, timestamp=None):
    schemas = {}
    cred_defs = {}
    rev_reg_defs = {}
    rev_regs = {}
    for item in identifiers:
        print("\"{}\" -> Get Schema from Ledger".format(actor))
        (received_schema_id, received_schema) = await get_schema(pool_handle, _did, item['schema_id'])
        schemas[received_schema_id] = json.loads(received_schema)

        print("\"{}\" -> Get Claim Definition from Ledger".format(actor))
        (received_cred_def_id, received_cred_def) = await get_cred_def(pool_handle, _did, item['cred_def_id'])
        cred_defs[received_cred_def_id] = json.loads(received_cred_def)

        if 'rev_reg_id' in item and item['rev_reg_id'] is not None:
            # Get Revocation Definitions and Revocation Registries
            print("\"{}\" -> Get Revocation Definition from Ledger".format(actor))
            get_revoc_reg_def_request = await ledger.build_get_revoc_reg_def_request(_did, item['rev_reg_id'])

            get_revoc_reg_def_response = \
                await ensure_previous_request_applied(pool_handle, get_revoc_reg_def_request,
                                                      lambda response: response['result']['data'] is not None)
            (rev_reg_id, revoc_reg_def_json) = await ledger.parse_get_revoc_reg_def_response(get_revoc_reg_def_response)

            print("\"{}\" -> Get Revocation Registry from Ledger".format(actor))
            if not timestamp: timestamp = item['timestamp']
            get_revoc_reg_request = \
                await ledger.build_get_revoc_reg_request(_did, item['rev_reg_id'], timestamp)
            get_revoc_reg_response = \
                await ensure_previous_request_applied(pool_handle, get_revoc_reg_request,
                                                      lambda response: response['result']['data'] is not None)
            (rev_reg_id, rev_reg_json, timestamp2) = await ledger.parse_get_revoc_reg_response(get_revoc_reg_response)

            rev_regs[rev_reg_id] = {timestamp2: json.loads(rev_reg_json)}
            rev_reg_defs[rev_reg_id] = json.loads(revoc_reg_def_json)

    return json.dumps(schemas), json.dumps(cred_defs), json.dumps(rev_reg_defs), json.dumps(rev_regs)


async def get_schema(pool_handle, _did, schema_id):
    get_schema_request = await ledger.build_get_schema_request(_did, schema_id)
    get_schema_response = await ensure_previous_request_applied(
        pool_handle, get_schema_request, lambda response: response['result']['data'] is not None)
    return await ledger.parse_get_schema_response(get_schema_response)



async def get_cred_def(pool_handle, _did, cred_def_id):
    get_cred_def_request = await ledger.build_get_cred_def_request(_did, cred_def_id)
    get_cred_def_response = \
        await ensure_previous_request_applied(pool_handle, get_cred_def_request,
                                              lambda response: response['result']['data'] is not None)
    return await ledger.parse_get_cred_def_response(get_cred_def_response)

async def ensure_previous_request_applied(pool_handle, checker_request, checker):
    for _ in range(3):
        response = json.loads(await ledger.submit_request(pool_handle, checker_request))
        try:
            if checker(response):
                return json.dumps(response)
        except TypeError:
            pass
        time.sleep(5)


async def create_wallet(identity):
    print("\"{}\" -> Create wallet".format(identity['name']))
    try:
        await wallet.create_wallet(identity['wallet_config'],
                                   identity['wallet_credentials'])
    except IndyError as ex:
        if ex.error_code == ErrorCode.PoolLedgerConfigAlreadyExistsError:
            pass
    identity['wallet'] = await wallet.open_wallet(identity['wallet_config'],
                                                  identity['wallet_credentials'])


async def getting_verinym(from_, to):
    await create_wallet(to)

    (to['did'], to['key']) = await did.create_and_store_my_did(to['wallet'], "{}")

    from_['info'] = {
        'did': to['did'],
        'verkey': to['key'],
        'role': to['role'] or None
    }

    await send_nym(from_['pool'], from_['wallet'], from_['did'], from_['info']['did'],
                   from_['info']['verkey'], from_['info']['role'])


async def send_nym(pool_handle, wallet_handle, _did, new_did, new_key, role):
    nym_request = await ledger.build_nym_request(_did, new_did, new_key, None, role)
    # print(nym_request)
    await ledger.sign_and_submit_request(pool_handle, wallet_handle, _did, nym_request)


async def get_credential_for_referent(search_handle, referent):
    credentials = json.loads(
        await anoncreds.prover_fetch_credentials_for_proof_req(search_handle, referent, 10))
    #print(credentials)
    return credentials[0]['cred_info']


async def prover_get_entities_from_ledger(pool_handle, _did, identifiers, actor, timestamp_from=None,
                                          timestamp_to=None):
    schemas = {}
    cred_defs = {}
    rev_states = {}
    # print(identifiers)
    for item in identifiers.values():
        print("\"{}\" -> Get Schema from Ledger".format(actor))
        (received_schema_id, received_schema) = await get_schema(pool_handle, _did, item['schema_id'])
        schemas[received_schema_id] = json.loads(received_schema)

        print("\"{}\" -> Get Claim Definition from Ledger".format(actor))
        (received_cred_def_id, received_cred_def) = await get_cred_def(pool_handle, _did, item['cred_def_id'])
        cred_defs[received_cred_def_id] = json.loads(received_cred_def)

        if 'rev_reg_id' in item and item['rev_reg_id'] is not None:
            # Create Revocations States
            print("\"{}\" -> Get Revocation Registry Definition from Ledger".format(actor))
            get_revoc_reg_def_request = await ledger.build_get_revoc_reg_def_request(_did, item['rev_reg_id'])

            get_revoc_reg_def_response = \
                await ensure_previous_request_applied(pool_handle, get_revoc_reg_def_request,
                                                      lambda response: response['result']['data'] is not None)
            (rev_reg_id, revoc_reg_def_json) = await ledger.parse_get_revoc_reg_def_response(get_revoc_reg_def_response)

            print("\"{}\" -> Get Revocation Registry Delta from Ledger".format(actor))
            if not timestamp_to: timestamp_to = int(time.time())
            get_revoc_reg_delta_request = \
                await ledger.build_get_revoc_reg_delta_request(_did, item['rev_reg_id'], timestamp_from, timestamp_to)
            get_revoc_reg_delta_response = \
                await ensure_previous_request_applied(pool_handle, get_revoc_reg_delta_request,
                                                      lambda response: response['result']['data'] is not None)
            (rev_reg_id, revoc_reg_delta_json, t) = \
                await ledger.parse_get_revoc_reg_delta_response(get_revoc_reg_delta_response)

            tails_reader_config = json.dumps(
                {'base_dir': dirname(json.loads(revoc_reg_def_json)['value']['tailsLocation']),
                 'uri_pattern': ''})
            blob_storage_reader_cfg_handle = await blob_storage.open_reader('default', tails_reader_config)

            print('%s - Create Revocation State', actor)
            rev_state_json = \
                await anoncreds.create_revocation_state(blob_storage_reader_cfg_handle, revoc_reg_def_json,
                                                        revoc_reg_delta_json, t, item['cred_rev_id'])
            rev_states[rev_reg_id] = {t: json.loads(rev_state_json)}

    return json.dumps(schemas), json.dumps(cred_defs), json.dumps(rev_states)



async def run():
    pool_ = {
    'name': 'pool1'
    }
    print("Open Pool Ledger: {}".format(pool_['name']))
    pool_['genesis_txn_path'] = "pool1.txn"
    pool_['config'] = json.dumps({"genesis_txn": str(pool_['genesis_txn_path'])})
    # Set protocol version 2 to work with Indy Node 1.4
    await pool.set_protocol_version(2)
    try:
        await pool.create_pool_ledger_config(pool_['name'], pool_['config'])
    except IndyError as ex:
        if ex.error_code == ErrorCode.PoolLedgerConfigAlreadyExistsError:
            pass
    pool_['handle'] = await pool.open_pool_ledger(pool_['name'], None)
    print(pool_['handle'])

    steward = {
        'name': "Sovrin Steward",
        'wallet_config': json.dumps({'id': 'sovrin_steward_wallet'}),
        'wallet_credentials': json.dumps({'key': 'steward_wallet_key'}),
        'pool': pool_['handle'],
        'seed': '000000000000000000000000Steward1'
    }
    #print(steward)

    await create_wallet(steward)

    #print(steward["wallet"])

    steward["did_info"] = json.dumps({'seed':steward['seed']})
    #print(steward["did_info"])

    # did:demoindynetwork:Th7MpTaRZVRYnPiabds81Y
    steward['did'], steward['key'] = await did.create_and_store_my_did(steward['wallet'], steward['did_info'])





    # ----------------------------------------------------------------------
    # Create and register dids for Government, University and CitiBank
    # 
    print("\n\n\n==============================")
    print("==  Government registering Verinym  ==")
    print("------------------------------")


    government = {
        'name': 'Government',
        'wallet_config': json.dumps({'id': 'government_wallet'}),
        'wallet_credentials': json.dumps({'key': 'government_wallet_key'}),
        'pool': pool_['handle'],
        'role': 'TRUST_ANCHOR'
    }

    await getting_verinym(steward, government)



    print("\n\n==============================")
    print("== IIT Kharagpur getting Verinym  ==")
    print("------------------------------")

    theUniversity = {
        'name': 'IIT Kharagpur',
        'wallet_config': json.dumps({'id': 'theUniversity_wallet'}),
        'wallet_credentials': json.dumps({'key': 'theUniversity_wallet_key'}),
        'pool': pool_['handle'],
        'role': 'TRUST_ANCHOR'
    }

    await getting_verinym(steward, theUniversity)


    print("\n\n==============================")
    print("== CitiBank getting Verinym  ==")
    print("------------------------------")

    citiBank = {
        'name': 'CitiBank',
        'wallet_config': json.dumps({'id': 'citiBank_wallet'}),
        'wallet_credentials': json.dumps({'key': 'citiBank_wallet_key'}),
        'pool': pool_['handle'],
        'role': 'TRUST_ANCHOR'
    }

    await getting_verinym(steward, citiBank)




    print("\n\n\n\"Government\" -> Create \"PropertyDetails\" Schema")
    propertyDetails = {
        'name': 'PropertyDetails',
        'version': '1.2',
        'attributes': ['owner_first_name', 'owner_last_name', 'address_of_property', 'owner_since_year', 'property_value_estimate']
    }

    (government['propertyDetails_schema_id'], government['propertyDetails_schema']) = \
        await anoncreds.issuer_create_schema(government['did'], propertyDetails['name'], propertyDetails['version'],
                                             json.dumps(propertyDetails['attributes']))
    
    #print(government['propertyDetails_schema'])
    propertyDetails_schema_id = government['propertyDetails_schema_id']

    #print(government['propertyDetails_schema_id'], government['propertyDetails_schema'])

    print("\"Government\" -> Send \"PropertyDetails\" Schema to Ledger")

    
    propertyDetails_schema_request = await ledger.build_schema_request(government['did'], government['propertyDetails_schema'])
    await ledger.sign_and_submit_request(government['pool'], government['wallet'], government['did'], propertyDetails_schema_request)




    print("\n\n\"Government\" -> Create \"BonafideStudent\" Schema")
    bonafideStudent = {
        'name': 'BonafideStudent',
        'version': '1.2',
        'attributes': ['student_first_name', 'student_last_name', 'course_name', 'student_since_year', 'department']
    }

    (government['bonafideStudent_schema_id'], government['bonafideStudent_schema']) = \
        await anoncreds.issuer_create_schema(government['did'], bonafideStudent['name'], bonafideStudent['version'],
                                             json.dumps(bonafideStudent['attributes']))
    
    #print(government['bonafideStudent_schema'])
    bonafideStudent_schema_id = government['bonafideStudent_schema_id']

    #print(government['bonafideStudent_schema_id'], government['bonafideStudent_schema'])

    print("\"Government\" -> Send \"BonafideStudent\" Schema to Ledger")

    
    bonafideStudent_schema_request = await ledger.build_schema_request(government['did'], government['bonafideStudent_schema'])
    await ledger.sign_and_submit_request(government['pool'], government['wallet'], government['did'], bonafideStudent_schema_request)



    # -----------------------------------------------------
    # IIT Kharagpur will create a credential definition
    
    print("\n\n==============================")
    print("=== IIT Kharagpur Credential Definition Setup ==")
    print("------------------------------")

    print("\"IIT Kharagpur\" -> Get \"BonafideStudent\" Schema from Ledger")


    # GET SCHEMA FROM LEDGER
    get_bonafideStudent_schema_request = await ledger.build_get_schema_request(theUniversity['did'], bonafideStudent_schema_id)
    get_bonafideStudent_schema_response = await ensure_previous_request_applied(
        theUniversity['pool'], get_bonafideStudent_schema_request, lambda response: response['result']['data'] is not None)
    (theUniversity['bonafideStudent_schema_id'], theUniversity['bonafideStudent_schema']) = await ledger.parse_get_schema_response(get_bonafideStudent_schema_response)

    # bonafideStudent CREDENTIAL DEFINITION
    print("\"IIT Kharagpur\" -> Create and store in Wallet \"IIT Kharagpur BonafideStudent\" Credential Definition")
    bonafideStudent_cred_def = {
        'tag': 'TAG1',
        'type': 'CL',
        'config': {"support_revocation": False}
    }
    (theUniversity['bonafideStudent_cred_def_id'], theUniversity['bonafideStudent_cred_def']) = \
        await anoncreds.issuer_create_and_store_credential_def(theUniversity['wallet'], theUniversity['did'],
                                                               theUniversity['bonafideStudent_schema'], bonafideStudent_cred_def['tag'],
                                                               bonafideStudent_cred_def['type'],
                                                               json.dumps(bonafideStudent_cred_def['config']))

    print("\"IIT Kharagpur\" -> Send  \"IIT Kharagpur bonafideStudent\" Credential Definition to Ledger")
    #print(theUniversity['bonafideStudent_cred_def'])

    bonafideStudent_cred_def_request = await ledger.build_cred_def_request(theUniversity['did'], theUniversity['bonafideStudent_cred_def'])
    #print(bonafideStudent_cred_def_request)
    await ledger.sign_and_submit_request(theUniversity['pool'], theUniversity['wallet'], theUniversity['did'], bonafideStudent_cred_def_request)





    # -----------------------------------------------------
    # Government will create a credential definition
    
    print("\n\n==============================")
    print("=== Government Credential Definition Setup ==")
    print("------------------------------")

    print("\"Government\" -> Get \"PropertyDetails\" Schema from Ledger")


    # GET SCHEMA FROM LEDGER
    get_propertyDetails_schema_request = await ledger.build_get_schema_request(government['did'], propertyDetails_schema_id)
    get_propertyDetails_schema_response = await ensure_previous_request_applied(
        government['pool'], get_propertyDetails_schema_request, lambda response: response['result']['data'] is not None)
    (government['propertyDetails_schema_id'], government['propertyDetails_schema']) = await ledger.parse_get_schema_response(get_propertyDetails_schema_response)

    # TRANSCRIPT CREDENTIAL DEFINITION
    print("\"Government\" -> Create and store in Wallet \"Government PropertyDetails\" Credential Definition")
    propertyDetails_cred_def = {
        'tag': 'TAG2',
        'type': 'CL',
        'config': {"support_revocation": False}
    }
    (government['propertyDetails_cred_def_id'], government['propertyDetails_cred_def']) = \
        await anoncreds.issuer_create_and_store_credential_def(government['wallet'], government['did'],
                                                               government['propertyDetails_schema'], propertyDetails_cred_def['tag'],
                                                               propertyDetails_cred_def['type'],
                                                               json.dumps(propertyDetails_cred_def['config']))

    print("\"Government\" -> Send  \"Government propertyDetails\" Credential Definition to Ledger")
    #print(government['propertyDetails_cred_def'])

    propertyDetails_cred_def_request = await ledger.build_cred_def_request(government['did'], government['propertyDetails_cred_def'])
    #print(propertyDetails_cred_def_request)
    await ledger.sign_and_submit_request(government['pool'], government['wallet'], government['did'], propertyDetails_cred_def_request)






    # ------------------------------------------------------------
    print("\n\n== Sunil setup ==")
    sunil = {
        'name': 'Sunil',
        'wallet_config': json.dumps({'id': 'sunil_wallet'}),
        'wallet_credentials': json.dumps({'key': 'sunil_wallet_key'}),
        'pool': pool_['handle'],
    }
    await create_wallet(sunil)
    (sunil['did'], sunil['key']) = await did.create_and_store_my_did(sunil['wallet'], "{}")





    # Sunil getting PropertyDetails from Government
    print("\n\n==============================")
    print("=== Getting PropertyDetails with Government ==")
    print("==============================")


    # Government creates PropertyDetails credential offer

    print("\"Government\" -> Create \"PropertyDetails\" Credential Offer for Sunil")
    government['propertyDetails_cred_offer'] = \
        await anoncreds.issuer_create_credential_offer(government['wallet'], government['propertyDetails_cred_def_id'])

    print("\"Government\" -> Send \"PropertyDetails\" Credential Offer to Sunil")
    
    # Over Network 
    sunil['propertyDetails_cred_offer'] = government['propertyDetails_cred_offer']

    #print(sunil['propertyDetails_cred_offer'])

    # Sunil prepares a PropertyDetails credential request

    propertyDetails_cred_offer_object = json.loads(sunil['propertyDetails_cred_offer'])

    sunil['propertyDetails_schema_id'] = propertyDetails_cred_offer_object['schema_id']
    sunil['propertyDetails_cred_def_id'] = propertyDetails_cred_offer_object['cred_def_id']

    print("\"Sunil\" -> Create and store \"Sunil\" Master Secret in Wallet")
    sunil['master_secret_id'] = await anoncreds.prover_create_master_secret(sunil['wallet'], None)

    print("\"Sunil\" -> Get \"Government PropertyDetails\" Credential Definition from Ledger")
    (sunil['government_propertyDetails_cred_def_id'], sunil['government_propertyDetails_cred_def']) = \
        await get_cred_def(sunil['pool'], sunil['did'], sunil['propertyDetails_cred_def_id'])

    print("\"Sunil\" -> Create \"PropertyDetails\" Credential Request for Government")
    (sunil['propertyDetails_cred_request'], sunil['propertyDetails_cred_request_metadata']) = \
        await anoncreds.prover_create_credential_req(sunil['wallet'], sunil['did'],
                                                     sunil['propertyDetails_cred_offer'],
                                                     sunil['government_propertyDetails_cred_def'],
                                                     sunil['master_secret_id'])

    print("\"Sunil\" -> Send \"PropertyDetails\" Credential Request to Government")

    #Over Network
    government['propertyDetails_cred_request'] = sunil['propertyDetails_cred_request']


    #University issues credential to Sunil ----------------
    print("\"Government\" -> Create \"propertyDetails\" Credential for Sunil")
    government['sunil_propertyDetails_cred_values'] = json.dumps({
        "owner_first_name": {"raw": "Sunil", "encoded": "1139481716457488690172217916278103335"},
        "owner_last_name": {"raw": "Dey", "encoded": "5321642780241790123587902456789123452"},
        "address_of_property": {"raw": "M G Road, Chennai", "encoded": "12434523576212321"},
        "owner_since_year": {"raw": "2005", "encoded": "2005"},
        "property_value_estimate": {"raw": "1000000", "encoded": "1000000"}
    })
    government['propertyDetails_cred'], _, _ = \
        await anoncreds.issuer_create_credential(government['wallet'], government['propertyDetails_cred_offer'],
                                                 government['propertyDetails_cred_request'],
                                                 government['sunil_propertyDetails_cred_values'], None, None)

    print("\"Government\" -> Send \"propertyDetails\" Credential to Sunil")
    #print(government['propertyDetails_cred'])
    # Over the network
    sunil['propertyDetails_cred'] = government['propertyDetails_cred']

    print("\"Sunil\" -> Store \"propertyDetails\" Credential from government")
    _, sunil['propertyDetails_cred_def'] = await get_cred_def(sunil['pool'], sunil['did'],
                                                         sunil['propertyDetails_cred_def_id'])

    await anoncreds.prover_store_credential(sunil['wallet'], None, sunil['propertyDetails_cred_request_metadata'],
                                            sunil['propertyDetails_cred'], sunil['propertyDetails_cred_def'], None)








    # Sunil getting bonafideStudent from IIT Kharagpur
    print("\n\n==============================")
    print("=== Getting bonafideStudent with IIT Kharagpur ==")
    print("==============================")


    # IIT Kharagpur creates bonafideStudent credential offer

    print("\"IIT Kharagpur\" -> Create \"bonafideStudent\" Credential Offer for Sunil")
    theUniversity['bonafideStudent_cred_offer'] = \
        await anoncreds.issuer_create_credential_offer(theUniversity['wallet'], theUniversity['bonafideStudent_cred_def_id'])

    print("\"IIT Kharagpur\" -> Send \"bonafideStudent\" Credential Offer to Sunil")
    
    # Over Network 
    sunil['bonafideStudent_cred_offer'] = theUniversity['bonafideStudent_cred_offer']

    #print(sunil['bonafideStudent_cred_offer'])

    # Sunil prepares a bonafideStudent credential request

    bonafideStudent_cred_offer_object = json.loads(sunil['bonafideStudent_cred_offer'])

    sunil['bonafideStudent_schema_id'] = bonafideStudent_cred_offer_object['schema_id']
    sunil['bonafideStudent_cred_def_id'] = bonafideStudent_cred_offer_object['cred_def_id']

    print("\"Sunil\" -> Create and store \"Sunil\" Master Secret in Wallet")
    sunil['master_secret_id'] = await anoncreds.prover_create_master_secret(sunil['wallet'], None)

    print("\"Sunil\" -> Get \"theUniversity bonafideStudent\" Credential Definition from Ledger")
    (sunil['theUniversity_bonafideStudent_cred_def_id'], sunil['theUniversity_bonafideStudent_cred_def']) = \
        await get_cred_def(sunil['pool'], sunil['did'], sunil['bonafideStudent_cred_def_id'])

    print("\"Sunil\" -> Create \"bonafideStudent\" Credential Request for IIT Kharagpur")
    (sunil['bonafideStudent_cred_request'], sunil['bonafideStudent_cred_request_metadata']) = \
        await anoncreds.prover_create_credential_req(sunil['wallet'], sunil['did'],
                                                     sunil['bonafideStudent_cred_offer'],
                                                     sunil['theUniversity_bonafideStudent_cred_def'],
                                                     sunil['master_secret_id'])

    print("\"Sunil\" -> Send \"bonafideStudent\" Credential Request to IIT Kharagpur")

    #Over Network
    theUniversity['bonafideStudent_cred_request'] = sunil['bonafideStudent_cred_request']


    #University issues credential to Sunil ----------------
    print("\"IIT Kharagpur\" -> Create \"bonafideStudent\" Credential for Sunil")
    theUniversity['sunil_bonafideStudent_cred_values'] = json.dumps({
        "student_first_name": {"raw": "Sunil", "encoded": "1139481716457488690172217916278103335"},
        "student_last_name": {"raw": "Dey", "encoded": "5321642780241790123587902456789123452"},
        "course_name": {"raw": "Mtech", "encoded": "12434523576212321"},
        "student_since_year": {"raw": "2021", "encoded": "2021"},
        "department": {"raw": "Computer Science and Engineering", "encoded": "12434523576212321"}
    })
    theUniversity['bonafideStudent_cred'], _, _ = \
        await anoncreds.issuer_create_credential(theUniversity['wallet'], theUniversity['bonafideStudent_cred_offer'],
                                                 theUniversity['bonafideStudent_cred_request'],
                                                 theUniversity['sunil_bonafideStudent_cred_values'], None, None)

    print("\"IIT Kharagpur\" -> Send \"bonafideStudent\" Credential to Sunil")
    #print(theUniversity['bonafideStudent_cred'])
    # Over the network
    sunil['bonafideStudent_cred'] = theUniversity['bonafideStudent_cred']

    print("\"Sunil\" -> Store \"bonafideStudent\" Credential from IIT Kharagpur")
    _, sunil['bonafideStudent_cred_def'] = await get_cred_def(sunil['pool'], sunil['did'],
                                                         sunil['bonafideStudent_cred_def_id'])

    await anoncreds.prover_store_credential(sunil['wallet'], None, sunil['bonafideStudent_cred_request_metadata'],
                                            sunil['bonafideStudent_cred'], sunil['bonafideStudent_cred_def'], None)


    # Verifiable Presentation

    # Creating application request (presentaion request) --- validator - theCompany
    print("\n\n\n\"CitiBank\" -> Create \"Loan-Application\" Proof Request")
    nonce = await anoncreds.generate_nonce()
    #citiBank = {}
    citiBank['loan_application_proof_request'] = json.dumps({
        'nonce': nonce,
        'name': 'Loan-Application',
        'version': '0.1',
        'requested_attributes': {
            'attr1_referent': {
                'name': 'student_first_name'
            },
            'attr2_referent': {
                'name': 'student_last_name'
            },
            'attr3_referent': {
                'name': 'course_name',
                'restrictions': [{'cred_def_id': theUniversity['bonafideStudent_cred_def_id']}]
            },
            'attr4_referent': {
                'name': 'address_of_property',
                'restrictions': [{'cred_def_id': government['propertyDetails_cred_def_id']}]
            },
            'attr5_referent': {
                'name': 'owner_since_year',
                'restrictions': [{'cred_def_id': government['propertyDetails_cred_def_id']}]
            }
        },
        'requested_predicates': {
            'predicate1_referent': {
                'name': 'student_since_year',
                'p_type': '>=',
                'p_value': 2021,
                'restrictions': [{'cred_def_id': theUniversity['bonafideStudent_cred_def_id']}]
            },
            'predicate2_referent': {
                'name': 'property_value_estimate',
                'p_type': '>',
                'p_value': 400000,
                'restrictions': [{'cred_def_id': government['propertyDetails_cred_def_id']}]
            }
        }
    })

    print("\"CitiBank\" -> Send \"Loan-Application\" Proof Request to Sunil")

    # Over Network
    sunil['loan_application_proof_request'] = citiBank['loan_application_proof_request']

    #print(sunil['loan_application_proof_request'])

    # Sunil prepares the presentation ===================================
    print("\"Sunil\" -> Get credentials for \"Loan-Application\" Proof Request")

    search_for_loan_application_proof_request = \
        await anoncreds.prover_search_credentials_for_proof_req(sunil['wallet'],
                                                                sunil['loan_application_proof_request'], None)
    
    # print("---------------------------")
    #print(search_for_loan_application_proof_request)
    # print("---------------------------")

    cred_for_attr1 = await get_credential_for_referent(search_for_loan_application_proof_request, 'attr1_referent')
    cred_for_attr2 = await get_credential_for_referent(search_for_loan_application_proof_request, 'attr2_referent')
    cred_for_attr3 = await get_credential_for_referent(search_for_loan_application_proof_request, 'attr3_referent')
    cred_for_attr4 = await get_credential_for_referent(search_for_loan_application_proof_request, 'attr4_referent')
    cred_for_attr5 = await get_credential_for_referent(search_for_loan_application_proof_request, 'attr5_referent')
    cred_for_predicate1 = \
        await get_credential_for_referent(search_for_loan_application_proof_request, 'predicate1_referent')
    cred_for_predicate2 = \
        await get_credential_for_referent(search_for_loan_application_proof_request, 'predicate2_referent')    
    
    #print("---------------------------")
    #print(cred_for_attr1)
    #print("---------------------------")


    await anoncreds.prover_close_credentials_search_for_proof_req(search_for_loan_application_proof_request)

    sunil['creds_for_loan_application_proof'] = {cred_for_attr1['referent']: cred_for_attr1,
                                                cred_for_attr2['referent']: cred_for_attr2,
                                                cred_for_attr3['referent']: cred_for_attr3,
                                                cred_for_attr4['referent']: cred_for_attr4,
                                                cred_for_attr5['referent']: cred_for_attr5,
                                                cred_for_predicate1['referent']: cred_for_predicate1,
                                                cred_for_predicate2['referent']: cred_for_predicate2}

    sunil['schemas_for_loan_application'], sunil['cred_defs_for_loan_application'], \
    sunil['revoc_states_for_loan_application'] = \
        await prover_get_entities_from_ledger(sunil['pool'], sunil['did'],
                                              sunil['creds_for_loan_application_proof'], sunil['name'])

    print("\"Sunil\" -> Create \"Loan-Application\" Proof")
    sunil['loan_application_requested_creds'] = json.dumps({
        'self_attested_attributes': {
            'attr1_referent': 'Sunil',
            'attr2_referent': 'Dey'
        },
        'requested_attributes': {
            'attr3_referent': {'cred_id': cred_for_attr3['referent'], 'revealed': True},
            'attr4_referent': {'cred_id': cred_for_attr4['referent'], 'revealed': True},
            'attr5_referent': {'cred_id': cred_for_attr5['referent'], 'revealed': True},
        },
        'requested_predicates': {
            'predicate1_referent': {'cred_id': cred_for_predicate1['referent']},
            'predicate2_referent': {'cred_id': cred_for_predicate2['referent']}
        }
    })

    #print(sunil['loan_application_requested_creds'])

    sunil['loan_application_proof'] = \
        await anoncreds.prover_create_proof(sunil['wallet'], sunil['loan_application_proof_request'],
                                            sunil['loan_application_requested_creds'], sunil['master_secret_id'],
                                            sunil['schemas_for_loan_application'],
                                            sunil['cred_defs_for_loan_application'],
                                            sunil['revoc_states_for_loan_application'])
    #print(sunil['loan_application_proof'])

    print("\"sunil\" -> Send \"loan-Application\" Proof to citiBank")

    # Over Network
    citiBank['loan_application_proof'] = sunil['loan_application_proof']
    

    # Validating the verifiable presentation
    loan_application_proof_object = json.loads(citiBank['loan_application_proof'])

    citiBank['schemas_for_loan_application'], citiBank['cred_defs_for_loan_application'], \
    citiBank['revoc_ref_defs_for_loan_application'], citiBank['revoc_regs_for_loan_application'] = \
        await verifier_get_entities_from_ledger(citiBank['pool'], citiBank['did'],
                                                loan_application_proof_object['identifiers'], citiBank['name'])

    print("\"CitiBank\" -> Verify \"loan-Application\" Proof from sunil")
    assert 'Mtech' == \
           loan_application_proof_object['requested_proof']['revealed_attrs']['attr3_referent']['raw']
    assert 'M G Road, Chennai' == \
           loan_application_proof_object['requested_proof']['revealed_attrs']['attr4_referent']['raw']
    assert '2005' == \
           loan_application_proof_object['requested_proof']['revealed_attrs']['attr5_referent']['raw']

    assert 'Sunil' == loan_application_proof_object['requested_proof']['self_attested_attrs']['attr1_referent']
    assert 'Dey' == loan_application_proof_object['requested_proof']['self_attested_attrs']['attr2_referent']

    # print(citiBank['schemas_for_loan_application'])
    # print(citiBank['cred_defs_for_loan_application'])
    # print(citiBank['revoc_ref_defs_for_loan_application'])
    # print(citiBank['revoc_regs_for_loan_application'])
    # print(citiBank['loan_application_proof_request'])
    # print(citiBank['loan_application_proof'])



    assert await anoncreds.verifier_verify_proof(citiBank['loan_application_proof_request'], citiBank['loan_application_proof'],
                                                 citiBank['schemas_for_loan_application'],
                                                 citiBank['cred_defs_for_loan_application'],
                                                 citiBank['revoc_ref_defs_for_loan_application'],
                                                 citiBank['revoc_regs_for_loan_application'])



loop = asyncio.get_event_loop()
loop.run_until_complete(run())