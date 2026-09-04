// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "forge-std/Test.sol";
import "../src/InvariantVault.sol";

contract InvariantVaultTest is Test {
    InvariantVault internal vault;
    address internal actor = address(0xA11CE);

    function setUp() public {
        vault = new InvariantVault();
        vm.deal(actor, 10 ether);
    }

    function testFuzz_TotalDepositsMustTrackOutstandingBalance(uint96 amount) public {
        amount = uint96(bound(amount, 1, 10 ether));
        vm.prank(actor);
        vault.deposit{value: amount}();

        vm.prank(actor);
        vault.withdraw(amount);

        assertEq(vault.totalDeposits(), vault.balance(actor), "accounting invariant violated");
    }
}
