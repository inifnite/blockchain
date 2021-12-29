const FabricCAServices = require('fabric-ca-client');
const {Wallets, Gateway} = require('fabric-network');
const fs = require('fs');
const path = require('path');


async function create_wallet_user(conn_path, id) {
    const ccpPath = path.resolve(conn_path);
    const ccp = JSON.parse(fs.readFileSync(ccpPath,'utf8'));

    const caInfo = ccp.certificateAuthorities['ca.org'+id+'.example.com'];
	const caTLSCACerts = caInfo.tlsCACerts.pem;
	const ca = new FabricCAServices(caInfo.url, { trustedRoots: caTLSCACerts, verify: false }, caInfo.caName);

    const WalletPath = path.join(process.cwd(), 'wallet_' + id);
    const wallet = await Wallets.newFileSystemWallet(WalletPath);
    ////console.log(`Wallet path: ${WalletPath}`);

    var adminIdentity = await wallet.get("admin");

    const enrollment = await ca.enroll({ enrollmentID: 'admin', enrollmentSecret: 'adminpw' });
	const x509Identity = {
		credentials: {
			certificate: enrollment.certificate,
			privateKey: enrollment.key.toBytes(),
		},
		mspId: 'Org'+id+'MSP',
		type: 'X.509',
	};
    await wallet.put('admin', x509Identity);
	////console.log('Successfully enrolled admin user and imported it into the wallet');
    adminIdentity = await wallet.get('admin');


    const user_name = 'appUser' + id;
    // Check to see if we've already enrolled the user.
    const userIdentity = await wallet.get(user_name);
    if (userIdentity) {
      //  //console.log(`An identity for the user ${user_name} already exists in the wallet`);
    }
    else {
        // build a user object for authenticating with the CA
        const provider = wallet.getProviderRegistry().getProvider(adminIdentity.type);
        const adminUser = await provider.getUserContext(adminIdentity, 'admin');

        // Register the user, enroll the user, and import the new identity into the wallet.
        const secret = await ca.register({
            affiliation: 'org' + id + '.department1',
            enrollmentID: user_name,
            role: 'client'
        }, adminUser);
        const enrollment = await ca.enroll({
            enrollmentID: user_name,
            enrollmentSecret: secret
        });
        const x509Identity = {
            credentials: {
                certificate: enrollment.certificate,
                privateKey: enrollment.key.toBytes(),
            },
            mspId: 'Org'+id+'MSP',
            type: 'X.509',
        };
        await wallet.put(user_name, x509Identity);
        ////console.log(`Successfully registered and enrolled admin user ${user_name} and imported it into the wallet`);
    }
    
    const [contract, gateway] = await create_gateway(ccp, wallet, id);
    ////console.log(`in create_wallet_user function  =====>     contract${id} ----${contract}------${gateway}`);

    return [contract, gateway];
}


async function create_gateway(ccp ,wallet, id) {
    const gateway = new Gateway();
    await gateway.connect(ccp, { wallet, identity: 'appUser'+ id, discovery: { enabled: true, asLocalhost: true } });

    // Get the network (channel) our contract is deployed to.
    const network = await gateway.getNetwork('mychannel');

    // Get the contract from the network.
    const contract = await network.getContract('fabhouse');

    //gateway.disconnect();

    ////console.log(`contract${id} ----${contract}------${gateway}`);

    return [contract, gateway];
}



async function main() {
    var myArgs = process.argv.slice(2);
    //console.log('myArgs: ', myArgs);

    //var path1 = '../organizations/peerOrganizations/org1.example.com/connection-org1.json';
    //var path2 = '../organizations/peerOrganizations/org2.example.com/connection-org2.json';
    var path1 = myArgs[0];
    var path2 = myArgs[1];
    var test_case_path = myArgs[2];
    

    const [contract1, gateway1] = await create_wallet_user(path1,'1');
    const [contract2, gateway2] = await create_wallet_user(path2,'2');

    ////console.log(` ----${contract1}------`);
    ////console.log(` ----${contract2}------`);

    //var test_case_path = '../../../../testcase.txt';
    test_case_path = path.resolve(test_case_path);
    
    var data = fs.readFileSync(test_case_path,'utf8');

    var lines = data.split("\n");
    ////console.log(`${lines} \n ${lines.length}`);

    for(let i = 0; i < lines.length-1; i++) {
        var attr = lines[i].split(";");

        for(let j = 1; j < attr.length; j++) {
            attr[j] = attr[j].trim();
            ////console.log(` ----${attr[j]}------`);
        }

        var result = undefined;

        if(attr[1] == 'TransferHouse') {
            try {pre_result = await contract1.evaluateTransaction('ReadHouse', `${attr[2]}`);}
            catch(error) {
                console.log(attr, "\nERROR\n");
                continue;
            }

            pre_str = pre_result.toString();
            pre_str_split = pre_str.split("\":\"");
            pre_str_dsplit = pre_str_split[2].split("\",\"")
            ////console.log(pre_str_dsplit[0]);

            if(attr[0] == 'org1') try {
                if(pre_str_dsplit[0] != 'Org1MSP') {
                    console.log(attr, "\nERROR\n");
                    continue;
                }
                result = await contract1.submitTransaction(`${attr[1]}`,`${attr[2]}`,`${attr[3]}`);}
                catch(error) {}
            else try {
                if(pre_str_dsplit[0] != 'Org2MSP') {
                    console.log(attr, "\nERROR\n");
                    continue;
                }
                result = await contract2.submitTransaction(`${attr[1]}`,`${attr[2]}`,`${attr[3]}`);}
                catch(error) {}
        }
        else if(attr[1] == 'CreateHouse') {
            pre_result = await contract1.evaluateTransaction('HouseExists', `${attr[2]}`);
            if(pre_result.toString() == 'true') {
                console.log(attr, "\nERROR\n");
                continue;
            }
            
            if(attr[0] == 'org1') try {
                result = await contract1.submitTransaction(`${attr[1]}`,`${attr[2]}`,`${attr[3]}`,`${attr[4]}`);}
                catch (error) {}
            else try {
                result = await contract2.submitTransaction(`${attr[1]}`,`${attr[2]}`,`${attr[3]}`,`${attr[4]}`);}
                catch (error) {}
        }
        else if(attr[1] == 'ReadHouse'){
            try {result = await contract2.evaluateTransaction(`${attr[1]}`,`${attr[2]}`);}
            catch (error) {}
        }
        else if(attr[1] == 'GetAllHouses'){
            try {result = await contract1.evaluateTransaction(`${attr[1]}`);}
            catch (error) {}
        }
        else if(attr[1] == 'HouseExists'){
            if(attr[0] == 'org1') try {result = await contract1.evaluateTransaction(`${attr[1]}`,`${attr[2]}`);}
            catch (error) {}
        }
        if (result instanceof Error || typeof result == 'undefined') console.log(attr, "\nERROR\n");
        else {
            console.log(attr);
            console.log(result.toString(),"\n");}
    }

    // Disconnect from the gateway.
    // await gateway.disconnect();
    await gateway1.disconnect();
    await gateway2.disconnect();

}

main();