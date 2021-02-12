#!/usr/bin/env python3
# Copyright (c) 2014-2019 The Bitcoin Core developers
# Copyright (c) DeFi Blockchain Developers
# Distributed under the MIT software license, see the accompanying
# file COPYING or http://www.opensource.org/licenses/mit-license.php.
"""Test the Dakota anchorsC."""

from test_framework.test_framework import DefiTestFramework
from test_framework.util import assert_equal, wait_until

from decimal import Decimal
import time

class AnchorDakotaTest (DefiTestFramework):
    def set_test_params(self):
        self.num_nodes = 3
        self.extra_args = [
            [ "-dummypos=1", "-spv=1", "-fakespv=1", "-anchorquorum=2", '-amkheight=0', "-dakotaheight=0"],
            [ "-dummypos=1", "-spv=1", "-fakespv=1", "-anchorquorum=2", '-amkheight=0', "-dakotaheight=0"],
            [ "-dummypos=1", "-spv=1", "-fakespv=1", "-anchorquorum=2", '-amkheight=0', "-dakotaheight=0"],
        ]
        self.setup_clean_chain = True

    # Masternodes have to mint blocks in the last 2 weeks to be valid for
    # anchor teams, function here mines on all available nodes in turn.
    def initmasternodesforanchors(self, blocks):
        for i in range(0, blocks):
            block_count = self.nodes[i % self.num_nodes].getblockcount()

            # Make sure that generate successfully ioncrements the chain by one.
            while self.nodes[i % self.num_nodes].getblockcount() < block_count + 1:
                self.nodes[i % self.num_nodes].generate(1)

            # Make sure all nodes agree before creating the next block.
            self.sync_blocks()

    # Tiem is hours to move node time forward and blocks the number of blocks
    # to mine in each hour.
    def rotateandgenerate(self, hours, blocks):
        for increment in range(1, hours + 1):
            # Change node time time first.
            for i in range(0, self.num_nodes):
                self.nodes[i % self.num_nodes].set_mocktime(int(time.time() + (increment * 60 * 60)))
                self.nodes[i % self.num_nodes].setmocktime(int(time.time() + (increment * 60 * 60)))

            block_count = self.nodes[0].getblockcount()

            # Make sure that generate successfully ioncrements the chain by blocks
            while self.nodes[0].getblockcount() < block_count + blocks:
                self.nodes[0].generate(1)

            self.sync_blocks()

    def setlastheight(self, height):
        for i in range(0, self.num_nodes):
            self.nodes[int(i % self.num_nodes)].spv_setlastheight(height)

    # Send same anchor on each node
    def createanchor(self, reward_address):
        tx = self.nodes[0].spv_createanchor([{
            'txid': "a0d5a294be3cde6a8bddab5815b8c4cb1b2ebf2c2b8a4018205d6f8c576e8963",
            'vout': 3,
            'amount': 2262303,
            'privkey': "cStbpreCo2P4nbehPXZAAM3gXXY1sAphRfEhj7ADaLx8i2BmxvEP"}],
            reward_address,
            True,
            2000)
        for i in range(1, self.num_nodes):
            self.nodes[i].spv_sendrawtx(tx['txHex'])

    # Mine up to height.
    def mine_diff(self, height):
        if self.nodes[0].getblockcount() < height:
            self.nodes[0].generate(height - self.nodes[0].getblockcount())
            self.sync_all()

    def run_test(self):

        # Let init complete
        time.sleep(1)

        assert_equal(len(self.nodes[0].listmasternodes()), 8)
        assert_equal(len(self.nodes[0].spv_listanchors()), 0)

        anchorFrequency = 15

        # Create multiple active MNs
        self.initmasternodesforanchors(2 * anchorFrequency)

        wait_until(lambda: len(self.nodes[0].getanchorteams()['auth']) == 3 and len(self.nodes[0].getanchorteams()['confirm']) == 3, timeout=10)

        # Mo anchors created yet as we need three hours depth in chain
        assert_equal(len(self.nodes[0].spv_listanchorauths()), 0)

        # Move forward 3 hours and generate blocks to make data available
        # for the anchor auth team, block 3 hours deep required.
        self.rotateandgenerate(3, 5)

        # Mine up to block 60
        self.mine_diff(60)

        # Anchor data
        wait_until(lambda: len(self.nodes[0].spv_listanchorauths()) > 0 and self.nodes[0].spv_listanchorauths()[0]['signers'] == 3, timeout=10)

        auth = self.nodes[0].spv_listanchorauths()
        creation_height = auth[0]['creationHeight']
        assert_equal(auth[0]['blockHeight'], 15)

        hash15 = self.nodes[0].getblockhash(15)
        hash_creation = self.nodes[0].getblockhash(creation_height)
        block15 = self.nodes[0].getblock(hash15)
        block_creation = self.nodes[0].getblock(hash_creation)

        # Check the time
        time_diff = block_creation['time'] - block15['time']
        assert(time_diff > 3 * 60 * 60)

        # Bitcoin block 15
        self.setlastheight(15)

        reward_address = self.nodes[0].getnewaddress("", "legacy")

        # Create anchor
        self.createanchor(reward_address)

        # Anchor pending
        assert_equal(len(self.nodes[0].spv_listanchors()), 0)
        pending = self.nodes[0].spv_listanchorspending()
        assert_equal(len(pending), 1)
        assert_equal(pending[0]['btcBlockHeight'], 15)
        assert_equal(pending[0]['defiBlockHeight'], 15)
        assert_equal(pending[0]['rewardAddress'], reward_address)
        assert_equal(pending[0]['confirmations'], 1) # Bitcoin confirmations
        assert_equal(pending[0]['signatures'], 2)
        assert_equal(pending[0]['anchorCreationHeight'], creation_height)

        # Check these are consistent across anchors life
        btcHash = pending[0]['btcTxHash']
        dfiHash = pending[0]['defiBlockHash']

        # Trigger anchor check
        self.nodes[0].generate(1)

        # Anchor
        assert_equal(len(self.nodes[0].spv_listanchorsunrewarded()), 0)
        assert_equal(len(self.nodes[0].spv_listanchorspending()), 0)
        anchors = self.nodes[0].spv_listanchors()
        assert_equal(len(anchors), 1)
        assert_equal(anchors[0]['btcBlockHeight'], 15)
        assert_equal(anchors[0]['btcTxHash'], btcHash)
        assert_equal(anchors[0]['previousAnchor'], '0000000000000000000000000000000000000000000000000000000000000000')
        assert_equal(anchors[0]['defiBlockHeight'], 15)
        assert_equal(anchors[0]['defiBlockHash'], dfiHash)
        assert_equal(anchors[0]['rewardAddress'], reward_address)
        assert_equal(anchors[0]['confirmations'], 1) # Bitcoin confirmations
        assert_equal(anchors[0]['signatures'], 2)
        assert_equal(anchors[0]['anchorCreationHeight'], creation_height)
        assert_equal(anchors[0]['active'], False)

        # Still not active
        self.setlastheight(19)

        anchors = self.nodes[0].spv_listanchors()
        assert_equal(anchors[0]['confirmations'], 5) # Bitcoin confirmations
        assert_equal(anchors[0]['active'], False)

        # Activate here
        self.setlastheight(20)

        anchors = self.nodes[0].spv_listanchors()
        assert_equal(anchors[0]['confirmations'], 6) # Bitcoin confirmations
        assert_equal(anchors[0]['active'], True)

        unrewarded = self.nodes[0].spv_listanchorsunrewarded()
        assert_equal(len(unrewarded), 1)
        assert_equal(unrewarded[0]['btcHeight'], 15)
        assert_equal(unrewarded[0]['btcHash'], btcHash)
        assert_equal(unrewarded[0]['dfiHeight'], 15)
        assert_equal(unrewarded[0]['dfiHash'], dfiHash)

        wait_until(lambda: len(self.nodes[0].spv_listanchorrewardconfirms()) == 1 and self.nodes[0].spv_listanchorrewardconfirms()[0]['signers'] == 3, timeout=10)

        assert_equal(self.nodes[0].listcommunitybalances()['AnchorReward'], Decimal('6.10000000'))

        reward = self.nodes[0].listcommunitybalances()['AnchorReward']

        # Mine anchor reward
        self.nodes[0].generate(1)

        block_count = self.nodes[0].getblockcount() # 47
        block_hash = self.nodes[0].getblockhash(block_count)
        block = self.nodes[0].getblock(block_hash)

        # Reward should be reset and block contains two TXs
        assert_equal(self.nodes[0].listcommunitybalances()['AnchorReward'], Decimal('0.10000000'))
        assert_equal(len(block['tx']), 2)

        tx = block['tx'][1]
        raw_tx = self.nodes[0].getrawtransaction(tx, 1, block_hash)

        # Check reward
        assert_equal(len(raw_tx['vout']), 2)
        assert_equal(raw_tx['vout'][1]['value'], reward)
        assert_equal(raw_tx['vout'][1]['scriptPubKey']['addresses'][0], reward_address)

        # Check data from list transactions
        anchors = self.nodes[0].listanchors()
        assert_equal(anchors[0]['anchorHeight'], 15)
        assert_equal(anchors[0]['anchorHash'], dfiHash)
        assert_equal(anchors[0]['rewardAddress'], reward_address)
        assert_equal(anchors[0]['dfiRewardHash'], tx)
        assert_equal(anchors[0]['btcAnchorHeight'], 15)
        assert_equal(anchors[0]['btcAnchorHash'], btcHash)

if __name__ == '__main__':
    AnchorDakotaTest().main()
