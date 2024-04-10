// Developed by Cosys-Lab, University of Antwerp

#pragma once

#include "vehicles/car/api/CarApiBase.hpp"
#include "SkidVehicleMovementComponent.h"
#include "physics/Kinematics.hpp"
#include "SkidVehiclePawn.h"


class SkidVehiclePawnApi {
public:
	typedef msr::airlib::ImageCaptureBase ImageCaptureBase;

	SkidVehiclePawnApi(ASkidVehiclePawn* pawn, const msr::airlib::Kinematics::State* pawn_kinematics, msr::airlib::CarApiBase* vehicle_api);

	void updateMovement(const msr::airlib::CarApiBase::CarControls& controls);

	msr::airlib::CarApiBase::CarState getCarState() const;

	void reset();
	void update(float delta = 0);

	virtual ~SkidVehiclePawnApi();

private:
	USkidVehicleMovementComponent* movement_;
	msr::airlib::CarApiBase::CarControls last_controls_;
	ASkidVehiclePawn* pawn_;
	const msr::airlib::Kinematics::State* pawn_kinematics_;
	msr::airlib::CarApiBase* vehicle_api_;
};