// 0x5f98e7df527027bf3be825734f40f431968ab28d
// 18CS30019

// SPDX-License-Identifier: GPL-3.0
pragma solidity >=0.7.0 <0.9.0;

contract game {

uint256 bid1;
uint256 bid2;

address p1;
address p2;

uint i1;
uint i2;

uint c1;
uint c2;

uint r1;
uint r2;

bytes32 h1;
bytes32 h2;

int m1;
int m2;


constructor() {
    bid1 = 0;
    bid2 = 0;
        
    i1 = 0;
    i2 = 0;
        
    r1 = 0;
    r2 = 0;

    c1 = 0;
    c2 = 0;

    p1 = address(0);
    p2 = address(0);

    h1 = 0;
    h2 = 0;
        
    m1 = -1;
    m2 = -1;
}



function initialize() public payable returns (uint)  {
    uint256 amount = msg.value;
    
    require(amount > 1000000000000000);

    if(i1 == 0 ) {
        i1 = 1;
        bid1 = msg.value ;
        p1 = msg.sender;
        
        
        return 1;
    }
    else if(i2 == 0) {
        require(msg.value >= bid1);
        
        require(p1 != msg.sender) ;
        
        i2 = 1;
        bid2 = msg.value ;
        p2 = msg.sender;
        
        return 2;
    }
    else revert();
}


function commitmove(bytes32 hashMove) public returns (bool) {
    if(i1 == 0 || i2 == 0) return false;
    
    if(c1 == 0 && msg.sender == p1) {
        c1 = 1;
        h1 = hashMove;
        return true;
    }
    else if(c2 == 0 && msg.sender == p2) {
        c2 = 1;
        h2 = hashMove;
        return true;
    }
    else return false;
    
}

function getFirstChar(string memory str) private pure returns (int) {
if (bytes(str)[0] == 0x30) return 0;
else if (bytes(str)[0] == 0x31) return 1;
else if (bytes(str)[0] == 0x32) return 2;
else if (bytes(str)[0] == 0x33) return 3;
else if (bytes(str)[0] == 0x34) return 4;
else if (bytes(str)[0] == 0x35) return 5;
else return -1;
}

function revealmove(string memory revealedMove) public returns (int) {
    if(c1 == 0 || c2 == 0 ) return -1;
    
    
    if(p1 != msg.sender && p2 != msg.sender) return -1;
    
    int move = getFirstChar(revealedMove);
    if(move < 0) return -1;
    
    bytes memory strBytes = bytes(revealedMove);
    bytes memory result = new bytes(strBytes.length-1);
    for(uint i = 1; i < strBytes.length; i++) {
        result[i-1] = strBytes[i];
    }
    
    bytes32 hash_move = sha256(strBytes);
    
    if(msg.sender == p1 && h1 == hash_move) {
        r1 = 1 ;
        m1 = move;
    }
    else if(msg.sender == p2 && h2 == hash_move) {
        r2 = 1 ;
        m2 = move;
    }
    else return -1;
    
    if(r1 == 1 && r2 == 1) {
        if(m2 >= m1) {
            (payable(p2)).transfer(bid1 + bid2);
        }
        else (payable(p1)).transfer(bid1 + bid2);
        
        bid1 = 0;
        bid2 = 0;
        
        i1 = 0;
        i2 = 0;

        c1 = 0;
        c2 = 0;
        
        r1 = 0;
        r2 = 0;
        
        m1 = -1;
        m2 = -1;

        h1 = 0;
        h2 = 0;

        p1 = address(0);
        p2 = address(0);
    }
    return move;
    
}


function getBalance() public view returns (uint) {
    return address(this).balance;
}

function getPlayerId() public view returns (uint) {
    if(p1 == msg.sender) return 1;
    else if(p2 == msg.sender ) return 2;
    else return 0;
}

}