"""Exercise the web API with local WAV files for the same speaker."""
import argparse
from pathlib import Path

import httpx


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('first',type=Path,help='WAV starting with 주문할게요')
    parser.add_argument('follow',type=Path,help='Different WAV from the same speaker without the cue')
    parser.add_argument('--other',type=Path,help='Optional follow-up WAV from a different speaker')
    parser.add_argument('--url',default='http://127.0.0.1:8058')
    args = parser.parse_args()
    with httpx.Client(base_url=args.url,timeout=75.) as client:
        def send(path,mode='order_speaker',session=None):
            data = {'mode':mode}
            if session is not None:
                data['session'] = session
            return client.post('/kiosk/api/speech',files={'file':('sample.wav',path.read_bytes(),'audio/wav')},data=data)

        first = send(args.first).raise_for_status().json()
        assert first['status']=='confirmation_required' and first['text'],first
        token = first['candidate_id']
        try:
            assert send(args.follow,session=token).status_code==409
            for _ in range(2):
                confirmed = client.post('/kiosk/api/order-voice/confirm',json={'token':token}).raise_for_status().json()
                assert confirmed['session']==token,confirmed
            follow = send(args.follow,session=token).raise_for_status().json()
            assert follow['status']=='tracked' and follow['text'],follow
            no_session = send(args.follow).raise_for_status().json()
            assert no_session['status']=='cue_missing',no_session
            legacy = send(args.follow,mode='off').raise_for_status().json()
            assert legacy['selected']=='off' and legacy['text'],legacy
            print('First:',first['text'])
            print('Follow:',follow['text'])
            if args.other:
                other = send(args.other,session=token).raise_for_status().json()
                assert other['status']=='speaker_unclear' and not other['text'],other
                print('Different speaker:',other['status'])
        finally:
            client.post('/kiosk/api/order-voice/end',json={'token':token}).raise_for_status()
        assert send(args.follow,session=token).status_code==409
        assert client.post('/kiosk/api/order-voice/confirm',json={'token':token}).status_code==409
        print('PASS: confirmation, follow-up, legacy OFF and session end.')


if __name__=='__main__':
    main()
