// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/// @notice Small deterministic audit fixture used to exercise CYDRA's
/// repository → model → hypothesis → observation → finding lifecycle.
contract InvariantVault {
    mapping(address => uint256) private _balances;
    uint256 private _totalDeposits;

    function deposit() external payable {
        _balances[msg.sender] += msg.value;
        _totalDeposits += msg.value;
    }

    function withdraw(uint256 amount) external {
        require(amount <= _balances[msg.sender], "insufficient balance");
        _balances[msg.sender] -= amount;
        _totalDeposits -= amount;
        payable(msg.sender).transfer(amount);
    }

    function balance(address account) external view returns (uint256) {
        return _balances[account];
    }

    function totalDeposits() external view returns (uint256) {
        return _totalDeposits;
    }
}
